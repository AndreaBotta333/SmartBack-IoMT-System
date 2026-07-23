"""Test di persistenza e pubblicazione delle assegnazioni delle maglie."""

import os
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, call

from app.infrastructure.database import init_database
from app.infrastructure.mqtt import SmartBackMqttHandler


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


class RawSmartShirtDiscoveryTests(unittest.TestCase):
    def test_mqtt_reconnect_activates_only_assigned_simulated_shirts(self) -> None:
        handler = SmartBackMqttHandler(
            host="mosquitto",
            port=1883,
            posture_topic="smartback/normalized/posture",
            device_topic="smartback/normalized/device",
            alert_topic="smartback/alerts/posture",
            stale_seconds=10,
            posture_engine=Mock(),
            influx=Mock(),
            broadcast=Mock(),
            assignment_provider=lambda: [
                {"device_id": "sim-assigned", "patient_id": "patient-a"}
            ],
            simulated_device_provider=lambda: [
                "sim-assigned",
                "sim-available",
            ],
        )
        handler.publish_device_assignment = Mock()
        handler.publish_simulated_device = Mock()
        client = Mock()

        handler._on_connect(client, None, None, 0, None)

        handler.publish_device_assignment.assert_called_once_with(
            "sim-assigned", "patient-a"
        )
        self.assertEqual(
            handler.publish_simulated_device.call_args_list,
            [
                call("sim-assigned", active=True),
                call("sim-available", active=False),
            ],
        )

    def test_unsupported_packet_still_marks_physical_shirt_as_seen(self) -> None:
        seen = Mock()
        handler = SmartBackMqttHandler(
            host="mosquitto",
            port=1883,
            posture_topic="smartback/normalized/posture",
            device_topic="smartback/normalized/device",
            alert_topic="smartback/alerts/posture",
            stale_seconds=10,
            posture_engine=Mock(),
            influx=Mock(),
            broadcast=Mock(),
            device_seen=seen,
        )
        message = Mock()
        message.topic = "unisadiem/smartshirt/tshirt002/ECG"
        message.payload = b"this payload must not be parsed"

        handler._on_message(Mock(), None, message)

        seen.assert_called_once_with("tshirt002", "measured")

    def test_retained_battery_snapshot_does_not_mark_shirt_online(self) -> None:
        seen = Mock()
        handler = SmartBackMqttHandler(
            host="mosquitto",
            port=1883,
            posture_topic="smartback/normalized/posture",
            device_topic="smartback/normalized/device",
            alert_topic="smartback/alerts/posture",
            stale_seconds=10,
            posture_engine=Mock(),
            influx=Mock(),
            broadcast=Mock(),
            device_seen=seen,
        )
        message = Mock()
        message.topic = "smartback/normalized/device"
        message.retain = True
        message.payload = json.dumps({
            "schema_version": 1,
            "device_id": "tshirt002",
            "patient_id": "patient-a",
            "timestamp": 1784780000000,
            "type": "battery",
            "state_of_charge": 80,
            "charging": False,
            "quality": "measured",
        }).encode()

        handler._on_message(Mock(), None, message)

        seen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
