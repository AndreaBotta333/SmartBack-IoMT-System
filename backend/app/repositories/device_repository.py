"""Persistenza SQLite dell'inventario e delle assegnazioni delle maglie."""

import sqlite3
import threading
from typing import Any


class RepositoryConflict(Exception):
    """La scrittura viola un vincolo persistente."""


class DeviceRepository:
    def __init__(
        self,
        connection: sqlite3.Connection,
        lock: threading.RLock,
    ) -> None:
        self._connection = connection
        self._lock = lock

    def create_simulated(
        self,
        *,
        doctor_id: str,
        display_name: str,
        created_at: str,
    ) -> dict[str, Any]:
        with self._lock:
            next_number = self._connection.execute(
                "SELECT COALESCE(MAX(doctor_device_number),-1)+1 AS next_number "
                "FROM devices WHERE owner_doctor_id=?",
                (doctor_id,),
            ).fetchone()["next_number"]
            device_id = (
                f"sim-{doctor_id.removeprefix('usr_')}-{int(next_number)}"
            )
            try:
                self._connection.execute(
                    "INSERT INTO devices("
                    "device_id,display_name,owner_doctor_id,doctor_device_number,"
                    "source_type,first_seen_at,last_seen_at,quality,has_telemetry"
                    ") VALUES (?,?,?,?,?,?,?,?,0)",
                    (
                        device_id,
                        display_name,
                        doctor_id,
                        int(next_number),
                        "simulated",
                        created_at,
                        created_at,
                        "simulated",
                    ),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise RepositoryConflict from exc
        return {
            "device_id": device_id,
            "inventory_id": int(next_number),
            "display_name": display_name,
            "source_type": "simulated",
        }

    def claim_discovered(
        self,
        *,
        doctor_id: str,
        device_id: str,
        display_name: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            next_number = self._connection.execute(
                "SELECT COALESCE(MAX(doctor_device_number),-1)+1 AS next_number "
                "FROM devices WHERE owner_doctor_id=?",
                (doctor_id,),
            ).fetchone()["next_number"]
            cursor = self._connection.execute(
                "UPDATE devices SET owner_doctor_id=?,doctor_device_number=?,"
                "display_name=? WHERE device_id=? AND owner_doctor_id IS NULL "
                "AND archived_at IS NULL AND has_telemetry=1",
                (doctor_id, int(next_number), display_name, device_id),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                return None
            self._connection.commit()
        return {
            "device_id": device_id,
            "inventory_id": int(next_number),
            "display_name": display_name,
        }

    def owned_device(
        self,
        *,
        doctor_id: str,
        device_id: str,
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM devices WHERE device_id=? AND owner_doctor_id=? "
            "AND archived_at IS NULL",
            (device_id, doctor_id),
        ).fetchone()

    def active_for_patient(self, patient_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT devices.device_id,devices.display_name,"
            "devices.source_type,devices.last_seen_at "
            "FROM device_assignments assignments "
            "JOIN devices ON devices.device_id=assignments.device_id "
            "WHERE assignments.patient_id=? "
            "AND assignments.released_at IS NULL "
            "AND devices.archived_at IS NULL LIMIT 1",
            (patient_id,),
        ).fetchone()

    def assign(
        self,
        *,
        doctor_id: str,
        device_id: str,
        patient_id: str,
        assigned_at: str,
    ) -> None:
        with self._lock:
            if self.owned_device(
                doctor_id=doctor_id,
                device_id=device_id,
            ) is None:
                raise LookupError(device_id)
            try:
                self._connection.execute(
                    "INSERT INTO device_assignments("
                    "device_id,patient_id,assigned_at,assigned_by"
                    ") VALUES (?,?,?,?)",
                    (device_id, patient_id, assigned_at, doctor_id),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise RepositoryConflict from exc

    def release(
        self,
        *,
        doctor_id: str,
        device_id: str,
        released_at: str,
    ) -> sqlite3.Row | None:
        with self._lock:
            assignment = self._connection.execute(
                "SELECT assignments.id,devices.source_type "
                "FROM device_assignments assignments "
                "JOIN devices ON devices.device_id=assignments.device_id "
                "WHERE assignments.device_id=? "
                "AND assignments.released_at IS NULL "
                "AND devices.owner_doctor_id=?",
                (device_id, doctor_id),
            ).fetchone()
            if assignment is None:
                return None
            self._connection.execute(
                "UPDATE device_assignments SET released_at=?,released_by=? "
                "WHERE id=?",
                (released_at, doctor_id, assignment["id"]),
            )
            self._connection.commit()
            return assignment

    def remove(
        self,
        *,
        doctor_id: str,
        device_id: str,
        removed_at: str,
    ) -> sqlite3.Row | None:
        with self._lock:
            device = self._connection.execute(
                "SELECT devices.source_type,assignments.patient_id "
                "FROM devices LEFT JOIN device_assignments assignments "
                "ON assignments.device_id=devices.device_id "
                "AND assignments.released_at IS NULL "
                "WHERE devices.device_id=? AND devices.owner_doctor_id=? "
                "AND devices.archived_at IS NULL",
                (device_id, doctor_id),
            ).fetchone()
            if device is None:
                return None
            self._connection.execute(
                "UPDATE device_assignments SET released_at=?,released_by=? "
                "WHERE device_id=? AND released_at IS NULL",
                (removed_at, doctor_id, device_id),
            )
            if device["source_type"] == "simulated":
                self._connection.execute(
                    "UPDATE devices SET archived_at=? WHERE device_id=?",
                    (removed_at, device_id),
                )
            else:
                self._connection.execute(
                    "UPDATE devices SET owner_doctor_id=NULL,"
                    "doctor_device_number=NULL,archived_at=NULL "
                    "WHERE device_id=?",
                    (device_id,),
                )
            self._connection.commit()
            return device
