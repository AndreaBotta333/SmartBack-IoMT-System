import os
import tempfile
import unittest

from fastapi import HTTPException

from app import main as main_module
from app.database import init_database


class FakeMqttHandler:
    def __init__(self) -> None:
        self.scenarios: list[tuple[str, str]] = []

    def publish_simulation_scenario(self, device_id: str, scenario: str) -> None:
        self.scenarios.append((device_id, scenario))


class NightMonitoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db = main_module.auth_db
        self.original_mqtt_handler = main_module.mqtt_handler
        main_module.mqtt_handler = None
        self.directory = tempfile.TemporaryDirectory()
        self.database = init_database(os.path.join(self.directory.name, "smartback.db"))
        self.database.executescript("""
            INSERT INTO users(
                id,name,email,password_hash,password_salt,role,created_at,patient_code
            ) VALUES (
                'patient-1','Paziente Uno','patient@example.test','x','x',
                'patient','2026-07-20T20:00:00+00:00','patient-demo-001'
            );
            INSERT INTO users(
                id,name,email,password_hash,password_salt,role,created_at,professional_verified
            ) VALUES (
                'doctor-1','Medico Uno','doctor@example.test','x','x',
                'doctor','2026-07-20T20:00:00+00:00',1
            );
            INSERT INTO doctor_patients(doctor_id,patient_id,created_at)
            VALUES ('doctor-1','patient-1','2026-07-20T20:00:00+00:00');
            INSERT INTO device_assignments(device_id,patient_id,assigned_at)
            VALUES ('tshirt002','patient-1','2026-07-20T20:00:00+00:00');
        """)
        self.database.commit()
        main_module.auth_db = self.database

    def tearDown(self) -> None:
        main_module.auth_db = self.original_db
        main_module.mqtt_handler = self.original_mqtt_handler
        self.database.close()
        self.directory.cleanup()

    def user(self, user_id: str):
        return self.database.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()

    def test_patient_starts_and_stops_a_session_with_assigned_shirt(self) -> None:
        patient = self.user("patient-1")
        started = main_module.start_night_monitoring(user=patient)
        self.assertEqual(started["mode"], "night")
        self.assertTrue(started["active"])
        self.assertEqual(started["session"]["device_id"], "tshirt002")
        self.assertEqual(started["session"]["status"], "active")

        stopped = main_module.stop_night_monitoring(user=patient)
        self.assertEqual(stopped["mode"], "day")
        self.assertFalse(stopped["active"])
        self.assertEqual(stopped["session"]["status"], "completed")
        self.assertEqual(stopped["session"]["end_reason"], "patient")

    def test_only_one_active_session_is_allowed(self) -> None:
        patient = self.user("patient-1")
        main_module.start_night_monitoring(user=patient)
        with self.assertRaises(HTTPException) as raised:
            main_module.start_night_monitoring(user=patient)
        self.assertEqual(raised.exception.status_code, 409)

    def test_patient_needs_an_active_device_assignment(self) -> None:
        self.database.execute(
            "UPDATE device_assignments SET released_at='2026-07-20T21:00:00+00:00'"
        )
        self.database.commit()
        with self.assertRaises(HTTPException) as raised:
            main_module.start_night_monitoring(user=self.user("patient-1"))
        self.assertEqual(raised.exception.status_code, 409)

    def test_doctor_cannot_activate_night_mode_for_patient(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            main_module.start_night_monitoring(user=self.user("doctor-1"))
        self.assertEqual(raised.exception.status_code, 403)

    def test_associated_doctor_can_read_patient_history(self) -> None:
        patient = self.user("patient-1")
        main_module.start_night_monitoring(user=patient)
        main_module.stop_night_monitoring(user=patient)
        result = main_module.night_monitoring_history(
            patient_id="patient-1", limit=50, user=self.user("doctor-1")
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["patient_id"], "patient-1")
        self.assertEqual(result["items"][0]["summary"]["supine_seconds"], 0)

    def test_simulated_shirt_switches_scenario_with_night_mode(self) -> None:
        self.database.execute(
            "UPDATE devices SET source_type='simulated' WHERE device_id='tshirt002'"
        )
        self.database.commit()
        fake_mqtt = FakeMqttHandler()
        main_module.mqtt_handler = fake_mqtt

        main_module.start_night_monitoring(user=self.user("patient-1"))
        main_module.stop_night_monitoring(user=self.user("patient-1"))

        self.assertEqual(fake_mqtt.scenarios, [
            ("tshirt002", "night-cycle"),
            ("tshirt002", "day-cycle"),
        ])


if __name__ == "__main__":
    unittest.main()
