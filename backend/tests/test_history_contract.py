"""Test del contratto condiviso per gli storici diurni e gli alert."""

import unittest
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app import bootstrap as main_module
from app.infrastructure.influx import InfluxManager
from app.bootstrap import (
    GrafanaLoginRequest,
    accessible_patient,
    normalize_history_range,
)


class GrafanaLoginContractTests(unittest.TestCase):
    def test_admin_identifier_does_not_require_email_syntax(self) -> None:
        request = GrafanaLoginRequest(
            email="admin", password="smartback-dev-password"
        )
        self.assertEqual(request.email, "admin")


class HistoryRangeTests(unittest.TestCase):
    def test_legacy_minutes_range_remains_supported(self) -> None:
        end = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
        start, normalized_end, minutes = normalize_history_range(
            minutes=60, start=None, end=end
        )
        self.assertEqual(normalized_end, end)
        self.assertEqual(start, end - timedelta(hours=1))
        self.assertEqual(minutes, 60)

    def test_custom_range_reports_its_duration(self) -> None:
        start = datetime(2026, 7, 10, tzinfo=timezone.utc)
        end = datetime(2026, 7, 17, tzinfo=timezone.utc)
        normalized_start, normalized_end, minutes = normalize_history_range(
            minutes=60, start=start, end=end
        )
        self.assertEqual(normalized_start, start)
        self.assertEqual(normalized_end, end)
        self.assertEqual(minutes, 10_080)

    def test_invalid_range_is_rejected(self) -> None:
        instant = datetime(2026, 7, 17, tzinfo=timezone.utc)
        with self.assertRaises(HTTPException) as raised:
            normalize_history_range(minutes=60, start=instant, end=instant)
        self.assertEqual(raised.exception.status_code, 422)

    def test_common_dashboard_ranges_are_supported(self) -> None:
        end = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
        for minutes in (60, 1_440, 10_080, 43_200):
            with self.subTest(minutes=minutes):
                start, normalized_end, normalized_minutes = normalize_history_range(
                    minutes=minutes, start=None, end=end
                )
                self.assertEqual(normalized_end, end)
                self.assertEqual(normalized_minutes, minutes)
                self.assertEqual(start, end - timedelta(minutes=minutes))

    def test_range_over_366_days_is_rejected(self) -> None:
        end = datetime(2026, 7, 17, tzinfo=timezone.utc)
        with self.assertRaises(HTTPException) as raised:
            normalize_history_range(
                minutes=60,
                start=end - timedelta(days=366, seconds=1),
                end=end,
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_minutes_are_capped_at_366_days(self) -> None:
        end = datetime(2026, 7, 17, tzinfo=timezone.utc)
        start, _, minutes = normalize_history_range(
            minutes=999_999, start=None, end=end
        )
        self.assertEqual(minutes, 527_040)
        self.assertEqual(start, end - timedelta(days=366))


class HistoryClassificationTests(unittest.TestCase):
    def test_axis_status_uses_independent_thresholds(self) -> None:
        self.assertEqual(InfluxManager._axis_status(4, 10, 20), "neutral")
        self.assertEqual(InfluxManager._axis_status(-12, 10, 20), "moderate")
        self.assertEqual(InfluxManager._axis_status(25, 10, 20), "marked")

    def test_alerts_are_grouped_by_monitoring_session(self) -> None:
        alerts = [
            {"timestamp": "2026-07-20T10:05:00+00:00", "session_id": "session-b"},
            {"timestamp": "2026-07-20T09:00:00+00:00", "session_id": None},
            {"timestamp": "2026-07-20T10:00:00+00:00", "session_id": "session-b"},
        ]
        sessions = InfluxManager.group_alerts_by_session(alerts)
        self.assertEqual(sessions[0]["session_id"], "session-b")
        self.assertEqual(sessions[0]["alert_count"], 2)
        self.assertEqual(sessions[1]["label"], "Sessione precedente")


class HistoryAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db = main_module.auth_db
        self.database = sqlite3.connect(":memory:")
        self.database.row_factory = sqlite3.Row
        self.database.executescript("""
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                patient_code TEXT
            );
            CREATE TABLE doctor_patients (
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL
            );
            INSERT INTO users VALUES ('patient-1', 'patient', 'patient-demo-001');
            INSERT INTO users VALUES ('patient-2', 'patient', 'patient-demo-002');
            INSERT INTO users VALUES ('doctor-1', 'doctor', NULL);
            INSERT INTO users VALUES ('doctor-2', 'doctor', NULL);
            INSERT INTO doctor_patients VALUES ('doctor-1', 'patient-1');
        """)
        main_module.auth_db = self.database

    def tearDown(self) -> None:
        main_module.auth_db = self.original_db
        self.database.close()

    def user(self, user_id: str) -> sqlite3.Row:
        return self.database.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()

    def test_patient_can_read_only_their_own_history(self) -> None:
        patient = self.user("patient-1")
        self.assertEqual(accessible_patient(patient)["id"], "patient-1")
        with self.assertRaises(HTTPException) as raised:
            accessible_patient(patient, "patient-2")
        self.assertEqual(raised.exception.status_code, 403)

    def test_doctor_can_read_an_associated_patient(self) -> None:
        selected = accessible_patient(self.user("doctor-1"), "patient-1")
        self.assertEqual(selected["patient_code"], "patient-demo-001")

    def test_doctor_cannot_read_an_unassociated_patient(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            accessible_patient(self.user("doctor-2"), "patient-1")
        self.assertEqual(raised.exception.status_code, 403)

    def test_doctor_must_select_a_patient(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            accessible_patient(self.user("doctor-1"))
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
