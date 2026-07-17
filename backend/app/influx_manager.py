"""InfluxDB persistence and query operations."""

import math
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
        minutes = min(max(minutes, 1), 10080)
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
