import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


class PatientRepository:
    def __init__(self, database: sqlite3.Connection, lock: threading.RLock):
        self.database = database
        self.lock = lock

    def by_fiscal_code(self, fiscal_code: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE fiscal_code=? AND role='patient'",
            (fiscal_code,),
        ).fetchone()

    def by_id(self, patient_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE id=? AND role='patient'", (patient_id,)
        ).fetchone()

    def create_pending(self, values: tuple[Any, ...]) -> sqlite3.Row:
        with self.lock:
            self.database.execute(
                "INSERT INTO users("
                "id,name,first_name,last_name,email,password_hash,password_salt,"
                "role,created_at,patient_code,fiscal_code,professional_verified,"
                "account_registered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
                values,
            )
            self.database.commit()
        patient = self.by_id(str(values[0]))
        if patient is None:
            raise RuntimeError("Paziente appena creato non trovato")
        return patient

    def doctor_links(self, patient_id: str) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT doctor_id FROM doctor_patients WHERE patient_id=?", (patient_id,)
        ).fetchall()

    def list_for_doctor(self, doctor_id: str) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT patients.*,links.created_at AS associated_at,"
            "EXISTS(SELECT 1 FROM night_monitoring_sessions nights "
            "WHERE nights.patient_id=patients.id AND nights.status='active') "
            "AS night_mode_active "
            "FROM doctor_patients links "
            "JOIN users patients ON patients.id=links.patient_id "
            "WHERE links.doctor_id=? ORDER BY patients.name COLLATE NOCASE",
            (doctor_id,),
        ).fetchall()

    def add_to_doctor(self, doctor_id: str, patient_id: str) -> None:
        with self.lock:
            self.database.execute(
                "INSERT INTO doctor_patients(doctor_id,patient_id,created_at) "
                "VALUES (?,?,?)",
                (doctor_id, patient_id, datetime.now(timezone.utc).isoformat()),
            )
            self.database.commit()

    def save_monitoring_config(
        self,
        *,
        patient_id: str,
        moderate_deviation_deg: float,
        marked_deviation_deg: float,
        moderate_roll_deg: float,
        marked_roll_deg: float,
        persistence_seconds: float,
        updated_by: str,
    ) -> None:
        self.database.execute(
            "INSERT INTO monitoring_configs("
            "patient_id,moderate_deviation_deg,marked_deviation_deg,"
            "moderate_roll_deg,marked_roll_deg,persistence_seconds,"
            "updated_at,updated_by) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(patient_id) DO UPDATE SET "
            "moderate_deviation_deg=excluded.moderate_deviation_deg,"
            "marked_deviation_deg=excluded.marked_deviation_deg,"
            "moderate_roll_deg=excluded.moderate_roll_deg,"
            "marked_roll_deg=excluded.marked_roll_deg,"
            "persistence_seconds=excluded.persistence_seconds,"
            "updated_at=excluded.updated_at,updated_by=excluded.updated_by",
            (
                patient_id,
                moderate_deviation_deg,
                marked_deviation_deg,
                moderate_roll_deg,
                marked_roll_deg,
                persistence_seconds,
                datetime.now(timezone.utc).isoformat(),
                updated_by,
            ),
        )
        self.database.commit()

    def delete_monitoring_config(self, patient_id: str) -> None:
        self.database.execute(
            "DELETE FROM monitoring_configs WHERE patient_id=?", (patient_id,)
        )
        self.database.commit()

    def remove_from_doctor(self, doctor_id: str, patient_id: str) -> list[sqlite3.Row]:
        assignments = self.database.execute(
            "SELECT assignments.id,assignments.device_id,devices.source_type "
            "FROM device_assignments assignments "
            "JOIN devices ON devices.device_id=assignments.device_id "
            "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
            "AND devices.owner_doctor_id=?",
            (patient_id, doctor_id),
        ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.database.execute(
                "UPDATE device_assignments SET released_at=?,released_by=? "
                "WHERE patient_id=? AND released_at IS NULL AND device_id IN "
                "(SELECT device_id FROM devices WHERE owner_doctor_id=?)",
                (now, doctor_id, patient_id, doctor_id),
            )
            self.database.execute(
                "DELETE FROM doctor_patients WHERE doctor_id=? AND patient_id=?",
                (doctor_id, patient_id),
            )
            self.database.commit()
        return assignments
