import sqlite3


class PortalRepository:
    """Letture aggregate necessarie alla Home del medico."""

    def __init__(self, database: sqlite3.Connection):
        self.database = database

    def patients_for_doctor(self, doctor_id: str) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT patients.*, links.created_at AS associated_at, "
            "assignments.device_id AS assigned_device "
            "FROM doctor_patients links "
            "JOIN users patients ON patients.id=links.patient_id "
            "LEFT JOIN device_assignments assignments "
            "ON assignments.patient_id=patients.id AND assignments.released_at IS NULL "
            "WHERE links.doctor_id=? ORDER BY patients.name COLLATE NOCASE",
            (doctor_id,),
        ).fetchall()

    def devices_for_doctor(self, doctor_id: str) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT devices.*, assignments.id AS assignment_id, "
            "assignments.patient_id, assignments.assigned_at, "
            "patients.patient_code, "
            "CASE WHEN links.doctor_id IS NOT NULL THEN patients.name "
            "ELSE NULL END AS patient_name "
            "FROM devices LEFT JOIN device_assignments assignments "
            "ON assignments.device_id=devices.device_id "
            "AND assignments.released_at IS NULL "
            "LEFT JOIN users patients ON patients.id=assignments.patient_id "
            "LEFT JOIN doctor_patients links ON links.patient_id=patients.id "
            "AND links.doctor_id=? "
            "WHERE devices.archived_at IS NULL AND devices.owner_doctor_id=? "
            "ORDER BY devices.doctor_device_number",
            (doctor_id, doctor_id),
        ).fetchall()

    def discovered_devices(self) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT device_id,last_seen_at,quality FROM devices "
            "WHERE owner_doctor_id IS NULL AND archived_at IS NULL "
            "AND has_telemetry=1 "
            "ORDER BY last_seen_at DESC,device_id COLLATE NOCASE"
        ).fetchall()
