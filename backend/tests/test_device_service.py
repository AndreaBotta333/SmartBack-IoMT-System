import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, call

from app.infrastructure.database import init_database
from app.repositories import DeviceRepository
from app.services import DeviceService
from app.services import (
    DeviceAssignmentNotFound,
    DeviceInventoryNotFound,
    DeviceNotFound,
)


class DeviceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = init_database(
            os.path.join(self.directory.name, "smartback.db")
        )
        self.database.execute(
            "INSERT INTO users("
            "id,name,email,password_hash,password_salt,role,created_at,"
            "patient_code"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                "patient-1",
                "Paziente Uno",
                "patient@example.test",
                "x",
                "x",
                "patient",
                "now",
                "patient-code-1",
            ),
        )
        self.database.commit()
        self.messaging = Mock()
        self.repository = DeviceRepository(
            self.database,
            threading.RLock(),
        )
        self.service = DeviceService(self.repository, self.messaging)

    def tearDown(self) -> None:
        self.database.close()
        self.directory.cleanup()

    def test_simulated_device_transmits_only_while_assigned(self) -> None:
        device = self.service.create_test_device(
            doctor_id="doctor-1",
            display_name="Maglia test",
        )
        device_id = str(device["device_id"])

        self.service.assign_device(
            doctor_id="doctor-1",
            device_id=device_id,
            patient_id="patient-1",
            patient_code="patient-code-1",
        )
        self.service.release_device(
            doctor_id="doctor-1",
            device_id=device_id,
        )

        self.assertEqual(
            self.messaging.publish_simulated_device.call_args_list,
            [
                call(device_id, active=False),
                call(device_id, active=True),
                call(device_id, active=False),
            ],
        )
        self.assertEqual(
            self.messaging.publish_device_assignment.call_args_list,
            [
                call(device_id, "patient-code-1"),
                call(device_id, None),
            ],
        )

    def test_removing_physical_device_releases_ownership_not_history(self) -> None:
        self.database.execute(
            "UPDATE devices SET owner_doctor_id='doctor-1',"
            "doctor_device_number=0 WHERE device_id='tshirt002'"
        )
        self.database.execute(
            "INSERT INTO device_assignments("
            "device_id,patient_id,assigned_at,assigned_by"
            ") VALUES ('tshirt002','patient-1','first','doctor-1')"
        )
        self.database.commit()

        self.service.remove_device(
            doctor_id="doctor-1",
            device_id="tshirt002",
        )

        device = self.database.execute(
            "SELECT owner_doctor_id,archived_at FROM devices "
            "WHERE device_id='tshirt002'"
        ).fetchone()
        assignment = self.database.execute(
            "SELECT released_at FROM device_assignments "
            "WHERE device_id='tshirt002'"
        ).fetchone()
        self.assertIsNone(device["owner_doctor_id"])
        self.assertIsNone(device["archived_at"])
        self.assertIsNotNone(assignment["released_at"])
        self.messaging.publish_device_assignment.assert_called_once_with(
            "tshirt002",
            None,
        )
        self.messaging.publish_simulated_device.assert_not_called()

    def test_inventory_errors_distinguish_missing_device_and_assignment(self):
        with self.assertRaises(DeviceInventoryNotFound):
            self.service.assign_device(
                doctor_id="doctor-1",
                device_id="missing",
                patient_id="patient-1",
                patient_code="patient-code-1",
            )

        with self.assertRaises(DeviceAssignmentNotFound):
            self.service.release_device(
                doctor_id="doctor-1",
                device_id="missing",
            )

        with self.assertRaises(DeviceNotFound):
            self.service.remove_device(
                doctor_id="doctor-1",
                device_id="missing",
            )


if __name__ == "__main__":
    unittest.main()
