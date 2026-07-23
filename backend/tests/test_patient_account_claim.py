"""Test del collegamento tra anagrafica clinica e account del paziente."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app import bootstrap as main_module
from app.infrastructure.database import init_database


class PatientAccountClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db = main_module.auth_db
        self.original_mqtt = main_module.mqtt_handler
        self.original_verified_grafana_user = main_module.verified_grafana_user
        main_module.mqtt_handler = None
        self.directory = tempfile.TemporaryDirectory()
        self.database = init_database(os.path.join(self.directory.name, "smartback.db"))
        self.database.executescript("""
            INSERT INTO users(
                id,name,email,password_hash,password_salt,role,created_at,
                professional_verified,account_registered
            ) VALUES (
                'doctor-1','Medico Uno','doctor@example.test','x','x','doctor',
                '2026-07-21T10:00:00+00:00',1,1
            );
            INSERT INTO users(
                id,name,email,password_hash,password_salt,role,created_at,
                professional_verified,account_registered
            ) VALUES (
                'doctor-2','Medico Due','doctor2@example.test','x','x','doctor',
                '2026-07-21T10:00:00+00:00',1,1
            );
            INSERT INTO sessions(token,user_id,created_at)
            VALUES ('grafana-doctor','doctor-1','2026-07-21T10:00:00+00:00');
        """)
        self.database.commit()
        main_module.auth_db = self.database
        main_module.verified_grafana_user = lambda _token: self.database.execute(
            "SELECT * FROM users WHERE id='doctor-1'"
        ).fetchone()

    def tearDown(self) -> None:
        main_module.auth_db = self.original_db
        main_module.mqtt_handler = self.original_mqtt
        main_module.verified_grafana_user = self.original_verified_grafana_user
        self.database.close()
        self.directory.cleanup()

    def test_doctor_creates_monitorable_patient_then_patient_claims_same_profile(self) -> None:
        associated = main_module.grafana_associate_patient(
            main_module.AssociatePatientRequest(fiscal_code="RSSMRA80A01H501U"),
            smartback_grafana_session="grafana-doctor",
        )
        patient_id = associated["id"]
        patient_code = associated["patient_code"]
        self.assertFalse(associated["account_registered"])
        self.assertEqual(associated["name"], "Utente non registrato")

        created_shirt = main_module.grafana_create_device(
            main_module.DeviceCreateRequest(display_name="Maglia test"),
            smartback_grafana_session="grafana-doctor",
        )
        main_module.grafana_assign_device(
            created_shirt["device_id"],
            main_module.DeviceAssignmentRequest(patient_code=patient_code),
            smartback_grafana_session="grafana-doctor",
        )

        registered = main_module.register(main_module.RegisterRequest(
            first_name="Mario",
            last_name="Rossi",
            email="mario.rossi@example.com",
            password="Password1!",
            role="patient",
            fiscal_code="RSSMRA80A01H501U",
        ))

        self.assertEqual(registered["user"]["id"], patient_id)
        self.assertEqual(registered["user"]["patient_code"], patient_code)
        self.assertTrue(registered["user"]["account_registered"])
        assignment = self.database.execute(
            "SELECT patient_id FROM device_assignments "
            "WHERE device_id=? AND released_at IS NULL",
            (created_shirt["device_id"],),
        ).fetchone()
        self.assertEqual(assignment["patient_id"], patient_id)
        link = self.database.execute(
            "SELECT 1 FROM doctor_patients WHERE doctor_id='doctor-1' AND patient_id=?",
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(link)

    def test_grafana_registration_creates_only_a_verified_doctor_and_session(self) -> None:
        response = main_module.Response()
        result = main_module.grafana_register_doctor(
            main_module.RegisterRequest(
                first_name="Giulia",
                last_name="Bianchi",
                email="giulia.bianchi@example.com",
                password="Password1!",
                role="doctor",
                medical_code=main_module.MEDICAL_REGISTRATION_CODE,
            ),
            response,
        )
        doctor = self.database.execute(
            "SELECT * FROM users WHERE email='giulia.bianchi@example.com'"
        ).fetchone()
        self.assertEqual(doctor["role"], "doctor")
        self.assertTrue(doctor["professional_verified"])
        self.assertEqual(result["redirect"], "/smartback/")
        self.assertIn(main_module.GRAFANA_SESSION_COOKIE, response.headers["set-cookie"])

    def test_patient_already_associated_with_another_doctor_has_clear_error(self) -> None:
        main_module.grafana_associate_patient(
            main_module.AssociatePatientRequest(fiscal_code="RSSMRA80A01H501U"),
            smartback_grafana_session="doctor-1",
        )
        main_module.verified_grafana_user = lambda _token: self.database.execute(
            "SELECT * FROM users WHERE id='doctor-2'"
        ).fetchone()

        with self.assertRaises(HTTPException) as raised:
            main_module.grafana_associate_patient(
                main_module.AssociatePatientRequest(fiscal_code="RSSMRA80A01H501U"),
                smartback_grafana_session="doctor-2",
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail,
            "Impossibile aggiungere il paziente perché è già associato a un altro medico",
        )

    def test_validation_messages_are_translated_to_italian(self) -> None:
        self.assertEqual(
            main_module.italian_validation_message({
                "type": "string_too_short",
                "loc": ("body", "fiscal_code"),
                "msg": "String should have at least 16 characters",
                "ctx": {"min_length": 16},
            }),
            "Il campo deve contenere almeno 16 caratteri",
        )
        self.assertEqual(
            main_module.italian_validation_message({
                "type": "value_error",
                "loc": ("body", "fiscal_code"),
                "msg": "Value error, Codice fiscale non valido",
            }),
            "Codice fiscale non valido",
        )

    def test_each_doctor_has_an_isolated_inventory_numbered_from_zero(self) -> None:
        doctors = {
            "doctor-1": self.database.execute(
                "SELECT * FROM users WHERE id='doctor-1'"
            ).fetchone(),
            "doctor-2": self.database.execute(
                "SELECT * FROM users WHERE id='doctor-2'"
            ).fetchone(),
        }
        main_module.verified_grafana_user = lambda token: doctors[token]

        first = main_module.grafana_create_device(
            main_module.DeviceCreateRequest(display_name="Maglia A"),
            smartback_grafana_session="doctor-1",
        )
        second = main_module.grafana_create_device(
            main_module.DeviceCreateRequest(display_name="Maglia B"),
            smartback_grafana_session="doctor-1",
        )
        other = main_module.grafana_create_device(
            main_module.DeviceCreateRequest(display_name="Maglia A"),
            smartback_grafana_session="doctor-2",
        )

        self.assertEqual([first["inventory_id"], second["inventory_id"]], [0, 1])
        self.assertEqual(other["inventory_id"], 0)
        doctor_one_devices = main_module.medical_portal_data(doctors["doctor-1"])["devices"]
        doctor_two_devices = main_module.medical_portal_data(doctors["doctor-2"])["devices"]
        self.assertEqual(
            [item["device_id"] for item in doctor_one_devices],
            [first["device_id"], second["device_id"]],
        )
        self.assertEqual(
            [item["device_id"] for item in doctor_two_devices],
            [other["device_id"]],
        )

    def test_detected_shirt_requires_explicit_claim(self) -> None:
        doctor = self.database.execute(
            "SELECT * FROM users WHERE id='doctor-2'"
        ).fetchone()
        main_module.verified_grafana_user = lambda _token: doctor
        main_module.register_seen_device("tshirt-detected", "good")

        before = main_module.medical_portal_data(doctor)
        self.assertEqual(before["devices"], [])
        self.assertEqual(
            [item["device_id"] for item in before["discovered_devices"]],
            ["tshirt-detected"],
        )

        claimed = main_module.grafana_claim_discovered_device(
            "tshirt-detected",
            main_module.DeviceClaimRequest(display_name="Maglia rilevata"),
            smartback_grafana_session="doctor-2",
        )
        self.assertEqual(claimed["inventory_id"], 0)
        after = main_module.medical_portal_data(doctor)
        self.assertEqual(after["discovered_devices"], [])
        self.assertEqual(after["devices"][0]["device_id"], "tshirt-detected")

    def test_portal_connection_status_expires_when_telemetry_stops(self) -> None:
        doctor = self.database.execute(
            "SELECT * FROM users WHERE id='doctor-1'"
        ).fetchone()
        current = datetime.now(timezone.utc)
        self.database.execute(
            "INSERT INTO devices("
            "device_id,display_name,owner_doctor_id,doctor_device_number,"
            "source_type,first_seen_at,last_seen_at,quality,has_telemetry"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "fresh-shirt",
                "Maglia recente",
                "doctor-1",
                0,
                "physical",
                current.isoformat(),
                current.isoformat(),
                "measured",
                1,
            ),
        )
        self.database.execute(
            "INSERT INTO devices("
            "device_id,display_name,owner_doctor_id,doctor_device_number,"
            "source_type,first_seen_at,last_seen_at,quality,has_telemetry"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "stale-shirt",
                "Maglia ferma",
                "doctor-1",
                1,
                "physical",
                current.isoformat(),
                (current - timedelta(seconds=main_module.DATA_STALE_SECONDS + 1)).isoformat(),
                "measured",
                1,
            ),
        )
        self.database.commit()

        devices = {
            item["device_id"]: item
            for item in main_module.medical_portal_data(doctor)["devices"]
        }
        self.assertTrue(devices["fresh-shirt"]["has_telemetry"])
        self.assertTrue(devices["fresh-shirt"]["connected"])
        self.assertTrue(devices["stale-shirt"]["has_telemetry"])
        self.assertFalse(devices["stale-shirt"]["connected"])


if __name__ == "__main__":
    unittest.main()
