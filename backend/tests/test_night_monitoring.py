"""Test delle API e della persistenza del monitoraggio notturno."""

import os
import tempfile
import unittest

from fastapi import HTTPException

from app import bootstrap as main_module
from app.infrastructure.database import init_database


class FakeMqttHandler:
    def __init__(self) -> None:
        self.scenarios: list[tuple[str, str]] = []

    def publish_simulation_scenario(self, device_id: str, scenario: str) -> None:
        self.scenarios.append((device_id, scenario))


class FakeInfluxManager:
    def __init__(self) -> None:
        self.night_states: list[dict[str, object]] = []

    def persist_night_session_state(self, **state: object) -> None:
        self.night_states.append(state)


class NightMonitoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db = main_module.auth_db
        self.original_mqtt_handler = main_module.mqtt_handler
        self.original_posture_engine = main_module.posture_engine
        self.original_influx_manager = main_module.influx_manager
        main_module.mqtt_handler = None
        main_module.posture_engine = None
        main_module.influx_manager = None
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
            INSERT INTO users(
                id,name,email,password_hash,password_salt,role,created_at,professional_verified
            ) VALUES (
                'doctor-2','Medico Due','doctor2@example.test','x','x',
                'doctor','2026-07-20T20:00:00+00:00',1
            );
            INSERT INTO sessions(token,user_id,created_at)
            VALUES ('grafana-doctor-1','doctor-1','2026-07-20T20:00:00+00:00');
            INSERT INTO sessions(token,user_id,created_at)
            VALUES ('grafana-doctor-2','doctor-2','2026-07-20T20:00:00+00:00');
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
        main_module.posture_engine = self.original_posture_engine
        main_module.influx_manager = self.original_influx_manager
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

    def test_start_and_stop_publish_live_session_state(self) -> None:
        fake_influx = FakeInfluxManager()
        main_module.influx_manager = fake_influx

        main_module.start_night_monitoring(user=self.user("patient-1"))
        main_module.stop_night_monitoring(user=self.user("patient-1"))

        self.assertEqual(len(fake_influx.night_states), 2)
        self.assertTrue(fake_influx.night_states[0]["active"])
        self.assertFalse(fake_influx.night_states[1]["active"])
        self.assertEqual(
            fake_influx.night_states[0]["session_id"],
            fake_influx.night_states[1]["session_id"],
        )
        self.assertEqual(fake_influx.night_states[0]["patient_code"], "patient-demo-001")

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

    def test_active_night_session_marks_patient_as_live_for_doctor(self) -> None:
        main_module.start_night_monitoring(user=self.user("patient-1"))

        result = main_module.doctor_patients(user=self.user("doctor-1"))

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["items"][0]["night_mode_active"])
        self.assertTrue(result["items"][0]["has_live_data"])

    def test_associated_doctor_can_start_and_stop_from_grafana(self) -> None:
        started = main_module.grafana_start_night_monitoring(
            patient_code="patient-demo-001",
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertEqual(started.status_code, 303)
        active = main_module.active_night_session("patient-1")
        self.assertIsNotNone(active)
        self.assertEqual(active["created_by"], "doctor-1")

        stopped = main_module.grafana_stop_night_monitoring(
            patient_code="patient-demo-001",
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertEqual(stopped.status_code, 303)
        completed = self.database.execute(
            "SELECT * FROM night_monitoring_sessions WHERE patient_id='patient-1'"
        ).fetchone()
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["end_reason"], "doctor")

    def test_grafana_status_reflects_session_started_by_patient(self) -> None:
        inactive = main_module.grafana_night_monitoring_status(
            patient_code="patient-demo-001",
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertFalse(inactive["active"])

        main_module.start_night_monitoring(user=self.user("patient-1"))

        active = main_module.grafana_night_monitoring_status(
            patient_code="patient-demo-001",
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertTrue(active["active"])
        self.assertIsNotNone(active["session_id"])

    def test_unassociated_doctor_cannot_control_night_mode(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            main_module.grafana_start_night_monitoring(
                patient_code="patient-demo-001",
                smartback_grafana_session="grafana-doctor-2",
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_doctor_can_store_manual_calibration_without_live_data(self) -> None:
        result = main_module.grafana_manual_calibration(
            patient_code="patient-demo-001",
            body=main_module.ManualCalibrationRequest(pitch_deg=-15.5, roll_deg=3.2),
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertEqual(result["reference_pitch_deg"], -15.5)
        self.assertEqual(result["reference_roll_deg"], 3.2)
        stored = self.database.execute(
            "SELECT * FROM device_calibrations WHERE device_id='tshirt002'"
        ).fetchone()
        self.assertEqual(stored["patient_id"], "patient-1")
        self.assertEqual(stored["calibrated_by"], "doctor-1")

        updated = main_module.grafana_manual_calibration(
            patient_code="patient-demo-001",
            body=main_module.ManualCalibrationRequest(pitch_deg=8.0),
            smartback_grafana_session="grafana-doctor-1",
        )
        self.assertEqual(updated["reference_pitch_deg"], 8.0)
        self.assertEqual(updated["reference_roll_deg"], 3.2)

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

    def test_patient_history_summary_aggregates_only_completed_sessions(self) -> None:
        self.database.executescript("""
            INSERT INTO night_monitoring_sessions(
                id,patient_id,device_id,status,started_at,ended_at,created_by,
                supine_seconds,prone_seconds,right_side_seconds,left_side_seconds
            ) VALUES
                ('night-completed','patient-1','tshirt002','completed',
                 '2026-07-20T22:00:00+00:00','2026-07-20T23:00:00+00:00','patient-1',
                 100,200,300,400),
                ('night-active','patient-1','tshirt002','active',
                 '2026-07-21T22:00:00+00:00',NULL,'patient-1',
                 900,900,900,900);
        """)
        self.database.commit()

        result = main_module.night_monitoring_history_summary(
            user=self.user("patient-1")
        )

        self.assertEqual(result["session_count"], 1)
        self.assertEqual(result["summary"]["supine_seconds"], 100)
        self.assertEqual(result["summary"]["left_side_seconds"], 400)

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

    def test_physical_shirt_is_not_sent_simulator_commands(self) -> None:
        fake_mqtt = FakeMqttHandler()
        main_module.mqtt_handler = fake_mqtt

        main_module._start_night_session(
            self.user("patient-1"), self.user("doctor-1")
        )
        main_module.stop_night_monitoring(user=self.user("patient-1"))

        self.assertEqual(fake_mqtt.scenarios, [])

    def test_patient_can_stop_session_started_by_doctor(self) -> None:
        started = main_module._start_night_session(
            self.user("patient-1"), self.user("doctor-1")
        )
        self.assertTrue(started["active"])

        stopped = main_module.stop_night_monitoring(user=self.user("patient-1"))

        self.assertFalse(stopped["active"])
        self.assertEqual(stopped["session"]["end_reason"], "patient")
        stored = self.database.execute(
            "SELECT created_by FROM night_monitoring_sessions "
            "WHERE id=?",
            (stopped["session"]["id"],),
        ).fetchone()
        self.assertEqual(stored["created_by"], "doctor-1")

    def test_active_simulated_session_is_restored_after_reconnect(self) -> None:
        self.database.execute(
            "UPDATE devices SET source_type='simulated' WHERE device_id='tshirt002'"
        )
        self.database.commit()
        main_module._start_night_session(
            self.user("patient-1"), self.user("doctor-1")
        )

        self.assertEqual(
            main_module.active_simulated_night_device_ids(), ["tshirt002"]
        )


if __name__ == "__main__":
    unittest.main()
