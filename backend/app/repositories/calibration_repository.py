"""Persistenza SQLite dei riferimenti di calibrazione posturale."""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


class CalibrationRepository:
    def __init__(self, database: sqlite3.Connection, lock: threading.RLock):
        self.database = database
        self.lock = lock

    def stored_reference(
        self, device_id: str, patient_code: str, algorithm_version: int
    ) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT calibrations.reference_pitch_deg,"
            "calibrations.reference_roll_deg "
            "FROM device_calibrations calibrations "
            "JOIN users patients ON patients.id=calibrations.patient_id "
            "WHERE calibrations.device_id=? AND patients.patient_code=? "
            "AND calibrations.algorithm_version=?",
            (device_id, patient_code, algorithm_version),
        ).fetchone()

    def reference_for_patient_device(
        self, device_id: str, patient_id: str, algorithm_version: int
    ) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT reference_pitch_deg,reference_roll_deg "
            "FROM device_calibrations WHERE device_id=? AND patient_id=? "
            "AND algorithm_version=?",
            (device_id, patient_id, algorithm_version),
        ).fetchone()

    def latest_for_patient(
        self, patient_id: str, algorithm_version: int
    ) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT reference_pitch_deg,reference_roll_deg,calibrated_at "
            "FROM device_calibrations WHERE patient_id=? "
            "AND algorithm_version=? ORDER BY calibrated_at DESC LIMIT 1",
            (patient_id, algorithm_version),
        ).fetchone()

    def active_device(self, patient_id: str) -> str | None:
        row = self.database.execute(
            "SELECT assignments.device_id FROM device_assignments assignments "
            "JOIN devices ON devices.device_id=assignments.device_id "
            "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
            "AND devices.archived_at IS NULL LIMIT 1",
            (patient_id,),
        ).fetchone()
        return str(row["device_id"]) if row else None

    def save(
        self,
        *,
        patient_id: str,
        calibrated_by: str,
        result: dict[str, Any],
        algorithm_version: int,
    ) -> None:
        with self.lock:
            self.database.execute(
                "INSERT INTO device_calibrations("
                "device_id,patient_id,reference_pitch_deg,reference_roll_deg,"
                "algorithm_version,calibrated_at,calibrated_by"
                ") VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET "
                "patient_id=excluded.patient_id,"
                "reference_pitch_deg=excluded.reference_pitch_deg,"
                "reference_roll_deg=excluded.reference_roll_deg,"
                "algorithm_version=excluded.algorithm_version,"
                "calibrated_at=excluded.calibrated_at,"
                "calibrated_by=excluded.calibrated_by",
                (
                    result["device_id"], patient_id,
                    result["reference_pitch_deg"], result["reference_roll_deg"],
                    algorithm_version, datetime.now(timezone.utc).isoformat(),
                    calibrated_by,
                ),
            )
            self.database.commit()
