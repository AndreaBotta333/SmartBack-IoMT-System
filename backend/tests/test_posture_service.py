import math
import unittest

from app.posture_service import PostureEngine, ThresholdProfile


PROFILE = ThresholdProfile(
    pitch_moderate_deg=10,
    pitch_marked_deg=20,
    roll_moderate_deg=10,
    roll_marked_deg=20,
    persistence_seconds=5,
)


def sample(*, timestamp: int, pitch_deg: float = 0, roll_deg: float = 0) -> dict:
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)
    return {
        "device_id": "test-shirt",
        "patient_id": "test-patient",
        "timestamp": timestamp,
        "x": math.sin(roll) * math.cos(pitch),
        "y": math.sin(pitch),
        "z": math.cos(roll) * math.cos(pitch),
    }


class PostureEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PostureEngine(
            lambda _: PROFILE,
            ema_alpha=1,
            hysteresis_deg=2,
        )
        baseline = self.engine.process(sample(timestamp=1_000))
        self.engine.calibrate("test-shirt", baseline)

    def test_pitch_and_roll_are_evaluated_independently(self) -> None:
        result = self.engine.process(sample(timestamp=2_000, pitch_deg=4, roll_deg=15))
        self.assertEqual(result["pitch_status"], "neutral")
        self.assertEqual(result["roll_status"], "moderate")
        self.assertEqual(result["dominant_axis"], "roll")
        self.assertEqual(result["posture_status"], "deviated")

    def test_persistence_promotes_roll_alert(self) -> None:
        self.engine.process(sample(timestamp=2_000, roll_deg=25))
        result = self.engine.process(sample(timestamp=8_000, roll_deg=25))
        self.assertEqual(result["roll_status"], "marked")
        self.assertEqual(result["posture_status"], "marked_deviation")
        self.assertEqual(result["alert"], "POSTURE_MARKED_DEVIATION")

    def test_hysteresis_prevents_threshold_chatter(self) -> None:
        self.engine.process(sample(timestamp=2_000, roll_deg=11))
        still_active = self.engine.process(sample(timestamp=3_000, roll_deg=9))
        neutral = self.engine.process(sample(timestamp=4_000, roll_deg=7))
        self.assertEqual(still_active["roll_status"], "moderate")
        self.assertEqual(neutral["roll_status"], "neutral")


if __name__ == "__main__":
    unittest.main()
