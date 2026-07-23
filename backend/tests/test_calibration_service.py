import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from app.services.calibration_service import (
    CalibrationConflict,
    CalibrationService,
)


class CalibrationServiceTest(unittest.TestCase):
    def service(self, sample):
        mqtt = Mock()
        mqtt.latest_posture = sample
        return CalibrationService(
            Mock(),
            mqtt=mqtt,
            influx=None,
            posture_engine=None,
            stale_seconds=10,
            algorithm_version=2,
            threshold_provider=Mock(),
            pending_samples={},
        )

    def test_capture_freezes_sample_at_click_time(self):
        sample = {
            "patient_id": "patient-1",
            "device_id": "shirt-1",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "pitch_deg": -15.0,
            "roll_deg": 3.0,
        }
        service = self.service(sample)
        service.capture("doctor-1", "patient-1")
        sample["pitch_deg"] = 20.0

        captured = service.consume_capture("doctor-1", "patient-1")
        self.assertEqual(captured["pitch_deg"], -15.0)
        self.assertEqual(captured["roll_deg"], 3.0)

    def test_sample_must_belong_to_patient_and_device(self):
        sample = {
            "patient_id": "patient-1",
            "device_id": "shirt-1",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        service = self.service(sample)

        with self.assertRaises(CalibrationConflict):
            service.fresh_sample("patient-2")
        with self.assertRaises(CalibrationConflict):
            service.fresh_sample("patient-1", "shirt-2")

    def test_missing_capture_cannot_be_confirmed(self):
        service = self.service(None)
        with self.assertRaises(CalibrationConflict) as raised:
            service.consume_capture("doctor-1", "patient-1")
        self.assertIn("Campione di calibrazione assente", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
