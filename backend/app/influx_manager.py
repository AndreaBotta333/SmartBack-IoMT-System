"""InfluxDB persistence and query operations."""

import math
from datetime import datetime, timezone
from typing import Any

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from app.posture_service import ThresholdProfile


class InfluxManager:
    def __init__(self, *, url: str, token: str, org: str, bucket: str) -> None:
        self.org = org
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def close(self) -> None:
        self.client.close()

    def is_ready(self) -> bool:
        try:
            return self.client.health().status == "pass"
        except Exception:
            return False

    def persist_posture(self, sample: dict[str, Any]) -> None:
        point = (
            Point("posture")
            .tag("device_id", sample["device_id"])
            .tag("patient_id", sample["patient_id"])
            .tag("status", sample["posture_status"])
            .tag("dominant_axis", sample["dominant_axis"])
            .tag("pitch_status", sample["pitch_status"])
            .tag("roll_status", sample["roll_status"])
            .field("pitch_deg", sample["pitch_deg"])
            .field("roll_deg", sample["roll_deg"])
            .field("raw_pitch_deg", sample["raw_pitch_deg"])
            .field("raw_roll_deg", sample["raw_roll_deg"])
            .field("reference_pitch_deg", sample["reference_pitch_deg"])
            .field("reference_roll_deg", sample["reference_roll_deg"])
            .field("pitch_deviation_deg", sample["pitch_deviation_deg"])
            .field("roll_deviation_deg", sample["roll_deviation_deg"])
            .field("deviation_deg", sample["deviation_deg"])
            .field("deviation_duration_seconds", sample["deviation_duration_seconds"])
            .field("alert_active", bool(sample["alert"]))
            .time(int(sample["timestamp"]), WritePrecision.MS)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=point)

    def query_posture_history(
        self,
        patient_code: str,
        minutes: int,
        profile: ThresholdProfile,
        limit: int = 600,
    ) -> list[dict[str, Any]]:
        minutes = min(max(minutes, 1), 527_040)
        limit = min(max(limit, 1), 1200)
        window_seconds = max(1, math.ceil(minutes * 60 / 240))
        query = f'''from(bucket: "{self.bucket}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r._measurement == "posture")
          |> filter(fn: (r) => r._field == "deviation_deg")
          |> filter(fn: (r) => r.patient_id == "{patient_code}")
          |> group(columns: ["patient_id"])
          |> aggregateWindow(every: {window_seconds}s, fn: mean, createEmpty: false)
          |> sort(columns: ["_time"])
          |> limit(n: {limit})'''
        tables = self.client.query_api().query(query=query, org=self.org)
        rows: list[dict[str, Any]] = []
        moderate = min(profile.pitch_moderate_deg, profile.roll_moderate_deg)
        marked = min(profile.pitch_marked_deg, profile.roll_marked_deg)
        for table in tables:
            for record in table.records:
                deviation = round(float(record.get_value()), 2)
                if abs(deviation) >= marked:
                    status = "marked_deviation"
                elif abs(deviation) >= moderate:
                    status = "deviated"
                else:
                    status = "neutral"
                rows.append({
                    "timestamp": record.get_time().isoformat(),
                    "deviation_deg": deviation,
                    "posture_status": status,
                    "is_incorrect": status != "neutral",
                })
        rows.sort(key=lambda item: item["timestamp"])
        return rows[-limit:]

    @staticmethod
    def _flux_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _axis_status(value: float, moderate: float, marked: float) -> str:
        absolute = abs(value)
        if absolute >= marked:
            return "marked"
        if absolute >= moderate:
            return "moderate"
        return "neutral"

    def query_posture_history_details(
        self,
        patient_code: str,
        *,
        start: datetime,
        end: datetime,
        profile: ThresholdProfile,
        limit: int = 600,
        stale_seconds: float = 10,
    ) -> dict[str, Any]:
        """Return the shared persistent history contract used by app and Grafana."""
        limit = min(max(limit, 10), 1200)
        duration_seconds = max(1, int((end - start).total_seconds()))
        window_seconds = max(1, math.ceil(duration_seconds / min(limit, 600)))
        safe_patient = self._flux_string(patient_code)
        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()
        fields = (
            "pitch_deg", "roll_deg", "pitch_deviation_deg", "roll_deviation_deg",
            "deviation_deg", "deviation_duration_seconds",
        )
        field_filter = " or ".join(f'r._field == "{field}"' for field in fields)
        query = f'''from(bucket: "{self.bucket}")
          |> range(start: time(v: "{start_iso}"), stop: time(v: "{end_iso}"))
          |> filter(fn: (r) => r._measurement == "posture" and r.patient_id == "{safe_patient}")
          |> filter(fn: (r) => {field_filter})
          |> group(columns: ["_field", "device_id"])
          |> aggregateWindow(every: {window_seconds}s, fn: mean, createEmpty: false)
          |> sort(columns: ["_time"])'''
        tables = self.client.query_api().query(query=query, org=self.org)
        samples: dict[tuple[str, str], dict[str, Any]] = {}
        for table in tables:
            for record in table.records:
                timestamp = record.get_time().astimezone(timezone.utc).isoformat()
                device_id = str(record.values.get("device_id", "unknown"))
                item = samples.setdefault(
                    (timestamp, device_id),
                    {"timestamp": timestamp, "device_id": device_id},
                )
                item[str(record.get_field())] = round(float(record.get_value()), 2)

        rows: list[dict[str, Any]] = []
        for item in sorted(samples.values(), key=lambda sample: sample["timestamp"]):
            pitch_deviation = float(item.get("pitch_deviation_deg", 0))
            roll_deviation = float(item.get("roll_deviation_deg", 0))
            dominant_axis = "pitch" if abs(pitch_deviation) >= abs(roll_deviation) else "roll"
            deviation = float(item.get(
                "deviation_deg",
                pitch_deviation if dominant_axis == "pitch" else roll_deviation,
            ))
            duration = float(item.get("deviation_duration_seconds", 0))
            pitch_status = self._axis_status(
                pitch_deviation, profile.pitch_moderate_deg, profile.pitch_marked_deg
            )
            roll_status = self._axis_status(
                roll_deviation, profile.roll_moderate_deg, profile.roll_marked_deg
            )
            marked = pitch_status == "marked" or roll_status == "marked"
            moderate = pitch_status != "neutral" or roll_status != "neutral"
            if marked and duration >= profile.persistence_seconds:
                posture_status = "marked_deviation"
            elif moderate and duration >= profile.persistence_seconds:
                posture_status = "prolonged_deviation"
            elif moderate:
                posture_status = "deviated"
            else:
                posture_status = "neutral"
            rows.append({
                **item,
                "pitch_deg": float(item.get("pitch_deg", 0)),
                "roll_deg": float(item.get("roll_deg", 0)),
                "pitch_deviation_deg": pitch_deviation,
                "roll_deviation_deg": roll_deviation,
                "deviation_deg": deviation,
                "deviation_duration_seconds": duration,
                "dominant_axis": dominant_axis,
                "pitch_status": pitch_status,
                "roll_status": roll_status,
                "posture_status": posture_status,
                "is_incorrect": posture_status != "neutral",
            })
        rows = rows[-limit:]

        gap_threshold = max(float(stale_seconds), float(window_seconds) * 2.5)
        gaps: list[dict[str, Any]] = []
        for previous, current in zip(rows, rows[1:]):
            previous_time = datetime.fromisoformat(previous["timestamp"])
            current_time = datetime.fromisoformat(current["timestamp"])
            gap_seconds = (current_time - previous_time).total_seconds()
            if gap_seconds > gap_threshold:
                gaps.append({
                    "start": previous["timestamp"],
                    "end": current["timestamp"],
                    "duration_seconds": round(gap_seconds, 1),
                })

        availability = self.query_posture_availability(patient_code)
        alerts = self.query_alert_history(
            patient_code, start=start, end=end, limit=min(limit, 200)
        )
        incorrect = sum(1 for row in rows if row["is_incorrect"])
        pitch_values = [abs(float(row["pitch_deviation_deg"])) for row in rows]
        roll_values = [abs(float(row["roll_deviation_deg"])) for row in rows]
        return {
            "items": rows,
            "count": len(rows),
            "range": {"start": start_iso, "end": end_iso},
            "aggregation_seconds": window_seconds,
            "availability": availability,
            "gaps": gaps,
            "alerts": alerts,
            "summary": {
                "samples": len(rows),
                "correct_percentage": round((len(rows) - incorrect) * 100 / len(rows), 1) if rows else 0,
                "incorrect_percentage": round(incorrect * 100 / len(rows), 1) if rows else 0,
                "average_pitch_deviation_deg": round(sum(pitch_values) / len(pitch_values), 1) if pitch_values else 0,
                "maximum_pitch_deviation_deg": round(max(pitch_values), 1) if pitch_values else 0,
                "average_roll_deviation_deg": round(sum(roll_values) / len(roll_values), 1) if roll_values else 0,
                "maximum_roll_deviation_deg": round(max(roll_values), 1) if roll_values else 0,
                "alert_events": len(alerts),
                "data_gaps": len(gaps),
                "gap_seconds": round(sum(gap["duration_seconds"] for gap in gaps), 1),
            },
        }

    def query_posture_availability(self, patient_code: str) -> dict[str, Any]:
        safe_patient = self._flux_string(patient_code)
        base = f'''from(bucket: "{self.bucket}")
          |> range(start: 0)
          |> filter(fn: (r) => r._measurement == "posture" and r._field == "deviation_deg")
          |> filter(fn: (r) => r.patient_id == "{safe_patient}")
          |> group(columns: ["patient_id"])'''
        query = f'''firstSample = {base} |> first() |> set(key: "boundary", value: "first")
lastSample = {base} |> last() |> set(key: "boundary", value: "last")
union(tables: [firstSample, lastSample])'''
        tables = self.client.query_api().query(query=query, org=self.org)
        boundaries: dict[str, str] = {}
        for table in tables:
            for record in table.records:
                boundary = str(record.values.get("boundary", ""))
                boundaries[boundary] = record.get_time().astimezone(timezone.utc).isoformat()
        return {
            "has_data": bool(boundaries),
            "first_timestamp": boundaries.get("first"),
            "last_timestamp": boundaries.get("last"),
        }

    def query_alert_history(
        self,
        patient_code: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        safe_patient = self._flux_string(patient_code)
        start_iso = start.astimezone(timezone.utc).isoformat()
        end_iso = end.astimezone(timezone.utc).isoformat()
        query = f'''from(bucket: "{self.bucket}")
          |> range(start: time(v: "{start_iso}"), stop: time(v: "{end_iso}"))
          |> filter(fn: (r) => r._measurement == "alerts" and r._field == "active")
          |> filter(fn: (r) => r.patient_id == "{safe_patient}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {min(max(limit, 1), 500)})'''
        tables = self.client.query_api().query(query=query, org=self.org)
        alerts: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                alerts.append({
                    "timestamp": record.get_time().astimezone(timezone.utc).isoformat(),
                    "code": record.values.get("code"),
                    "category": record.values.get("category"),
                    "severity": record.values.get("severity"),
                    "active": bool(record.get_value()),
                })
        alerts.sort(key=lambda item: item["timestamp"], reverse=True)
        return alerts[:limit]
