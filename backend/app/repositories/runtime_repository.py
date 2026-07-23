"""Persistenza richiesta dal runtime MQTT e dai motori di monitoraggio."""

import sqlite3
import threading
from datetime import datetime, timezone


class RuntimeRepository:
    def __init__(self, database: sqlite3.Connection, lock: threading.RLock):
        self.database = database
        self.lock = lock

    def register_seen_device(self, device_id: str, quality: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.database.execute(
                "INSERT INTO devices("
                "device_id,display_name,source_type,first_seen_at,last_seen_at,"
                "quality,has_telemetry) VALUES (?,?,?,?,?,?,1) "
                "ON CONFLICT(device_id) DO UPDATE SET "
                "last_seen_at=excluded.last_seen_at,"
                "quality=excluded.quality,has_telemetry=1,"
                "source_type=CASE WHEN excluded.quality='simulated' "
                "THEN 'simulated' ELSE devices.source_type END",
                (
                    device_id,
                    device_id,
                    "simulated" if quality == "simulated" else "physical",
                    now,
                    now,
                    quality,
                ),
            )
            self.database.commit()

    def active_assignments(self) -> list[dict[str, str]]:
        rows = self.database.execute(
            "SELECT assignments.device_id,patients.patient_code "
            "FROM device_assignments assignments "
            "JOIN users patients ON patients.id=assignments.patient_id "
            "WHERE assignments.released_at IS NULL"
        ).fetchall()
        return [
            {
                "device_id": str(row["device_id"]),
                "patient_id": str(row["patient_code"]),
            }
            for row in rows
        ]

    def simulated_device_ids(self) -> list[str]:
        rows = self.database.execute(
            "SELECT device_id FROM devices "
            "WHERE source_type='simulated' ORDER BY device_id"
        ).fetchall()
        return [str(row["device_id"]) for row in rows]

    def active_simulated_night_device_ids(self) -> list[str]:
        rows = self.database.execute(
            "SELECT nights.device_id FROM night_monitoring_sessions nights "
            "JOIN devices ON devices.device_id=nights.device_id "
            "WHERE nights.status='active' "
            "AND devices.source_type='simulated' "
            "AND devices.archived_at IS NULL"
        ).fetchall()
        return [str(row["device_id"]) for row in rows]

    def active_night_session_for_sample(
        self, device_id: str, patient_code: str
    ) -> dict[str, str] | None:
        row = self.database.execute(
            "SELECT nights.id,nights.patient_id,nights.device_id "
            "FROM night_monitoring_sessions nights "
            "JOIN users patients ON patients.id=nights.patient_id "
            "WHERE nights.status='active' AND nights.device_id=? "
            "AND patients.patient_code=?",
            (device_id, patient_code),
        ).fetchone()
        return dict(row) if row else None

    def active_night_sessions(self) -> list[dict[str, str]]:
        rows = self.database.execute(
            "SELECT nights.id,nights.device_id,patients.patient_code "
            "FROM night_monitoring_sessions nights "
            "JOIN users patients ON patients.id=nights.patient_id "
            "WHERE nights.status='active'"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_night_summary(
        self,
        session_id: str,
        position: str,
        elapsed_seconds: float,
        changed: bool,
    ) -> None:
        if elapsed_seconds <= 0:
            return
        columns = {
            "supine": "supine_seconds",
            "prone": "prone_seconds",
            "right_side": "right_side_seconds",
            "left_side": "left_side_seconds",
            "unknown": "unknown_seconds",
            "data_gap": "data_gap_seconds",
        }
        column = columns.get(position, "unknown_seconds")
        with self.lock:
            self.database.execute(
                f"UPDATE night_monitoring_sessions "
                f"SET {column}={column}+?,position_changes=position_changes+? "
                "WHERE id=? AND status='active'",
                (elapsed_seconds, 1 if changed else 0, session_id),
            )
            self.database.commit()

    def monitoring_config(self, patient_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT moderate_deviation_deg,marked_deviation_deg,"
            "moderate_roll_deg,marked_roll_deg,persistence_seconds "
            "FROM monitoring_configs WHERE patient_id=?",
            (patient_id,),
        ).fetchone()

    def patient_by_code(self, patient_code: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE patient_code=? AND role='patient'",
            (patient_code,),
        ).fetchone()
