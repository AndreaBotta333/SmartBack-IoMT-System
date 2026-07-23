import json
import unittest

from app.infrastructure.mqtt import SmartBackMqttHandler


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        self.messages.append(json.loads(payload))


class DaySessionTests(unittest.TestCase):
    def test_only_first_alert_transition_starts_episode(self) -> None:
        handler = SmartBackMqttHandler.__new__(SmartBackMqttHandler)
        handler.alert_topic = "smartback/alerts/posture"
        handler._last_posture_alert = {}
        handler._monitoring_session = {"shirt-1": "session-1"}
        client = FakeClient()
        sample = {
            "timestamp": 1,
            "device_id": "shirt-1",
            "patient_id": "patient-1",
            "deviation_deg": 12.0,
            "pitch_deviation_deg": 12.0,
            "roll_deviation_deg": 0.0,
            "dominant_axis": "pitch",
            "deviation_duration_seconds": 6.0,
        }

        handler._publish_posture_transition(
            client, {**sample, "alert": "POSTURE_PROLONGED_DEVIATION"}
        )
        handler._publish_posture_transition(
            client, {**sample, "alert": "POSTURE_MARKED_DEVIATION"}
        )
        handler._publish_posture_transition(client, {**sample, "alert": None})

        self.assertEqual(
            [message["episode_started"] for message in client.messages],
            [True, False, False],
        )
        self.assertTrue(all(message["session_id"] == "session-1" for message in client.messages))


if __name__ == "__main__":
    unittest.main()
