"""Test del coordinamento tra telemetria MQTT e stato persistente."""

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from app.infrastructure.database import init_database
from app.infrastructure.telemetry import TelemetryCoordinator
from app.repositories.runtime_repository import RuntimeRepository


class TelemetryCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_database = tempfile.NamedTemporaryFile(suffix=".db")
        self.database = init_database(self.temporary_database.name)
        self.repository = RuntimeRepository(
            self.database,
            threading.RLock(),
        )
        self.coordinator = TelemetryCoordinator(self.repository, 10.0)

    def tearDown(self):
        self.database.close()
        self.temporary_database.close()

    def test_connection_requires_recent_valid_telemetry(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(
            self.coordinator.is_connected(
                (now - timedelta(seconds=5)).isoformat(),
                now=now,
            )
        )
        self.assertFalse(
            self.coordinator.is_connected(
                (now - timedelta(seconds=11)).isoformat(),
                now=now,
            )
        )
        self.assertFalse(self.coordinator.is_connected("non-valid", now=now))

    def test_seen_device_is_persisted_as_telemetry_source(self):
        self.coordinator.register_seen_device("shirt-test", "good")
        row = self.database.execute(
            "SELECT * FROM devices WHERE device_id='shirt-test'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["source_type"], "physical")
        self.assertEqual(row["has_telemetry"], 1)

    def test_simulated_devices_are_exposed_to_mqtt_runtime(self):
        self.coordinator.register_seen_device("shirt-sim", "simulated")
        self.assertEqual(
            self.coordinator.simulated_device_ids(),
            ["shirt-sim"],
        )


if __name__ == "__main__":
    unittest.main()
