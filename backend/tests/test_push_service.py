import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from app.push_service import notification_for_alert, send_expo_push


class PushNotificationMappingTests(unittest.TestCase):
    def test_actionable_alerts_are_mapped_to_italian_notifications(self) -> None:
        notification = notification_for_alert({
            "code": "POSTURE_MARKED_DEVIATION",
            "active": True,
            "severity": "critical",
            "patient_id": "patient-1",
            "device_id": "tshirt002",
        })
        self.assertIsNotNone(notification)
        self.assertEqual(notification["channelId"], "posture_alerts_v2")
        self.assertEqual(notification["priority"], "high")

    def test_prolonged_posture_uses_requested_message(self) -> None:
        notification = notification_for_alert({
            "code": "POSTURE_PROLONGED_DEVIATION", "active": True,
        })
        self.assertEqual(notification["body"], "Fai una pausa e raddrizza la schiena.")

    def test_recovery_events_do_not_generate_push_notifications(self) -> None:
        self.assertIsNone(notification_for_alert({"code": "POSTURE_OK", "active": False}))
        self.assertIsNone(notification_for_alert({"code": "DATA_STREAM_RESTORED", "active": False}))

    def test_low_battery_and_stream_loss_are_actionable(self) -> None:
        self.assertEqual(notification_for_alert({"code": "BATTERY_LOW", "active": True})["channelId"], "smartshirt_alerts_v2")
        self.assertEqual(notification_for_alert({"code": "DATA_STREAM_STALE", "active": True})["channelId"], "smartshirt_alerts_v2")

    @patch("app.push_service.time.sleep", return_value=None)
    @patch("app.push_service.urllib.request.urlopen")
    def test_temporary_network_failure_is_retried(self, mocked_open, _mocked_sleep) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data":[{"status":"ok","id":"ticket-1"}]}'
        mocked_open.side_effect = [urllib.error.URLError("temporary DNS failure"), response]

        accepted = send_expo_push(
            ["ExponentPushToken[test]"],
            {"title": "Test", "body": "Test", "data": {"code": "TEST"}},
        )

        self.assertEqual(accepted, 1)
        self.assertEqual(mocked_open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
