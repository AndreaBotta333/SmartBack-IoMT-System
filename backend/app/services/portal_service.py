import sqlite3
from typing import Any, Callable

from app.repositories.portal_repository import PortalRepository


class PortalService:
    def __init__(
        self,
        repository: PortalRepository,
        user_serializer: Callable[[sqlite3.Row], dict[str, Any]],
        connection_checker: Callable[[str | None], bool],
    ):
        self.repository = repository
        self.user_serializer = user_serializer
        self.connection_checker = connection_checker

    def home(self, doctor: sqlite3.Row) -> dict[str, Any]:
        doctor_id = str(doctor["id"])
        patients = self.repository.patients_for_doctor(doctor_id)
        devices = self.repository.devices_for_doctor(doctor_id)
        discovered = self.repository.discovered_devices()
        patient_items = [
            {
                **self.user_serializer(row),
                "associated_at": row["associated_at"],
                "assigned_device": row["assigned_device"],
            }
            for row in patients
        ]
        device_items = [
            {
                "device_id": row["device_id"],
                "inventory_id": row["doctor_device_number"],
                "display_name": row["display_name"] or row["device_id"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "quality": row["quality"],
                "source_type": row["source_type"],
                "has_telemetry": bool(row["has_telemetry"]),
                "connected": self.connection_checker(row["last_seen_at"]),
                "available": row["assignment_id"] is None,
                "assigned_at": row["assigned_at"],
                "patient_code": row["patient_code"],
                "patient_name": row["patient_name"] or (
                    "Altro paziente" if row["assignment_id"] is not None else None
                ),
            }
            for row in devices
        ]
        return {
            "doctor": self.user_serializer(doctor),
            "patients": patient_items,
            "devices": device_items,
            "discovered_devices": [
                {"device_id": row["device_id"], "last_seen_at": row["last_seen_at"]}
                for row in discovered
            ],
            "summary": {
                "patients": len(patient_items),
                "devices_total": len(device_items),
                "devices_available": sum(
                    1 for item in device_items if item["available"]
                ),
                "devices_assigned": sum(
                    1 for item in device_items if not item["available"]
                ),
            },
        }
