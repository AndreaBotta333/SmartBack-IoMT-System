"""Test della composizione della Home medica."""

import tempfile
import unittest
from pathlib import Path

from app.infrastructure.database import init_database
from app.repositories.portal_repository import PortalRepository
from app.services.portal_service import PortalService


class PortalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        path = str(Path(self.directory.name) / "smartback.db")
        self.database = init_database(path)
        self.database.executemany(
            "INSERT INTO users("
            "id,name,email,password_hash,password_salt,role,created_at,"
            "patient_code,fiscal_code"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            (
                (
                    "doctor-1", "Medico Test", "doctor@example.test",
                    "digest", "salt", "doctor", "now", None, None,
                ),
                (
                    "patient-1", "Paziente Test", "patient@example.test",
                    "digest", "salt", "patient", "now", "patient-code",
                    "RSSMRA80A01H501U",
                ),
            ),
        )
        self.database.execute(
            "INSERT INTO doctor_patients(doctor_id,patient_id,created_at) "
            "VALUES ('doctor-1','patient-1','now')"
        )
        self.database.executemany(
            "INSERT INTO devices("
            "device_id,display_name,owner_doctor_id,doctor_device_number,"
            "source_type,first_seen_at,last_seen_at"
            ") VALUES (?,?,?,?,?,?,?)",
            (
                ("sim-z", "Maglia Zebra", "doctor-1", 0, "simulated", "now", "now"),
                ("sim-a", "Maglia Alfa", "doctor-1", 1, "simulated", "now", "now"),
            ),
        )
        self.database.execute(
            "INSERT INTO device_assignments("
            "device_id,patient_id,assigned_at,assigned_by"
            ") VALUES ('sim-z','patient-1','now','doctor-1')"
        )
        self.database.commit()

    def tearDown(self) -> None:
        self.database.close()
        self.directory.cleanup()

    def test_home_exposes_assigned_name_and_sorts_devices_by_name(self) -> None:
        repository = PortalRepository(self.database)
        service = PortalService(
            repository,
            user_serializer=lambda row: {
                "id": row["id"],
                "name": row["name"],
                "patient_code": row["patient_code"],
                "fiscal_code": row["fiscal_code"],
            },
            connection_checker=lambda _last_seen: False,
        )
        doctor = self.database.execute(
            "SELECT * FROM users WHERE id='doctor-1'"
        ).fetchone()

        home = service.home(doctor)

        self.assertEqual(
            home["patients"][0]["assigned_device_name"],
            "Maglia Zebra",
        )
        self.assertEqual(
            [device["display_name"] for device in home["devices"]],
            ["Maglia Alfa", "Maglia Zebra"],
        )


if __name__ == "__main__":
    unittest.main()
