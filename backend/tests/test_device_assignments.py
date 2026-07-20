import os
import sqlite3
import tempfile
import unittest

from app.database import init_database


class DeviceAssignmentSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = init_database(
            os.path.join(self.directory.name, "smartback.db")
        )
        self.database.execute(
            "INSERT INTO users(id,name,email,password_hash,password_salt,role,created_at,patient_code) "
            "VALUES ('patient-a','Paziente A','a@example.test','x','x','patient','now','patient-a')"
        )
        self.database.execute(
            "INSERT INTO users(id,name,email,password_hash,password_salt,role,created_at,patient_code) "
            "VALUES ('patient-b','Paziente B','b@example.test','x','x','patient','now','patient-b')"
        )
        self.database.execute(
            "INSERT INTO devices(device_id,first_seen_at,last_seen_at) "
            "VALUES ('shirt-1','now','now')"
        )
        self.database.commit()

    def tearDown(self) -> None:
        self.database.close()
        self.directory.cleanup()

    def test_a_shirt_has_only_one_active_patient(self) -> None:
        self.database.execute(
            "INSERT INTO device_assignments(device_id,patient_id,assigned_at) "
            "VALUES ('shirt-1','patient-a','now')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.execute(
                "INSERT INTO device_assignments(device_id,patient_id,assigned_at) "
                "VALUES ('shirt-1','patient-b','later')"
            )

    def test_released_shirt_can_be_reassigned_without_losing_history(self) -> None:
        self.database.execute(
            "INSERT INTO device_assignments(device_id,patient_id,assigned_at,released_at) "
            "VALUES ('shirt-1','patient-a','first','second')"
        )
        self.database.execute(
            "INSERT INTO device_assignments(device_id,patient_id,assigned_at) "
            "VALUES ('shirt-1','patient-b','third')"
        )
        rows = self.database.execute(
            "SELECT patient_id,released_at FROM device_assignments ORDER BY id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["patient_id"], "patient-a")
        self.assertIsNotNone(rows[0]["released_at"])
        self.assertEqual(rows[1]["patient_id"], "patient-b")
        self.assertIsNone(rows[1]["released_at"])

    def test_real_shirt_two_is_seeded_as_physical(self) -> None:
        shirt = self.database.execute(
            "SELECT display_name,source_type,has_telemetry FROM devices "
            "WHERE device_id='tshirt002'"
        ).fetchone()
        self.assertEqual(shirt["display_name"], "Maglia 2")
        self.assertEqual(shirt["source_type"], "physical")
        self.assertEqual(shirt["has_telemetry"], 0)

    def test_archiving_a_shirt_does_not_delete_assignment_history(self) -> None:
        self.database.execute(
            "INSERT INTO device_assignments(device_id,patient_id,assigned_at,released_at) "
            "VALUES ('shirt-1','patient-a','first','second')"
        )
        self.database.execute(
            "UPDATE devices SET archived_at='third' WHERE device_id='shirt-1'"
        )
        history = self.database.execute(
            "SELECT patient_id FROM device_assignments WHERE device_id='shirt-1'"
        ).fetchall()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["patient_id"], "patient-a")


if __name__ == "__main__":
    unittest.main()
