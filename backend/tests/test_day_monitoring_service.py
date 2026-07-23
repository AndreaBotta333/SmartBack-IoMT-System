"""Test delle statistiche e dello storico del monitoraggio diurno."""

import unittest
from unittest.mock import Mock

from app.services.day_monitoring_service import (
    DayArchiveUnavailable,
    DayMonitoringService,
)


class DayMonitoringServiceTest(unittest.TestCase):
    def test_statistics_are_calculated_from_persisted_samples(self):
        influx = Mock()
        influx.query_posture_history.return_value = [
            {"is_incorrect": False, "deviation_deg": 2.0},
            {"is_incorrect": True, "deviation_deg": -12.0},
        ]
        profile = object()
        service = DayMonitoringService(
            influx,
            threshold_provider=lambda _patient: profile,
            stale_seconds=5,
        )
        patient = {"id": "patient-1", "patient_code": "patient-code-1"}

        result = service.statistics(patient, 60)

        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["correct_percentage"], 50.0)
        self.assertEqual(result["incorrect_percentage"], 50.0)
        self.assertEqual(result["average_deviation_deg"], 7.0)
        self.assertEqual(result["maximum_deviation_deg"], 12.0)
        influx.query_posture_history.assert_called_once_with(
            "patient-code-1", 60, profile, 600
        )

    def test_statistics_range_is_limited_to_seven_days(self):
        influx = Mock()
        influx.query_posture_history.return_value = []
        service = DayMonitoringService(
            influx,
            threshold_provider=lambda _patient: object(),
            stale_seconds=5,
        )
        patient = {"id": "patient-1", "patient_code": "patient-code-1"}

        result = service.statistics(patient, 999_999)

        self.assertEqual(result["period_minutes"], 10_080)
        self.assertEqual(
            influx.query_posture_history.call_args.args[1],
            10_080,
        )

    def test_missing_archive_is_reported_by_the_service(self):
        service = DayMonitoringService(
            None,
            threshold_provider=lambda _patient: object(),
            stale_seconds=5,
        )
        with self.assertRaises(DayArchiveUnavailable):
            service.availability(
                {"id": "patient-1", "patient_code": "patient-code-1"}
            )


if __name__ == "__main__":
    unittest.main()
