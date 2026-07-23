import math
import unittest

from app.domain.posture import PostureEngine, ThresholdProfile


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
        # Assi della maglia reale: Y verticale, Z avanti/indietro.
        "y": math.cos(roll) * math.cos(pitch),
        "z": -math.sin(pitch),
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

    def test_pitch_and_roll_durations_are_independent(self) -> None:
        self.engine.process(sample(timestamp=2_000, pitch_deg=15))
        entered_roll = self.engine.process(
            sample(timestamp=4_000, pitch_deg=15, roll_deg=15)
        )
        result = self.engine.process(
            sample(timestamp=8_000, pitch_deg=15, roll_deg=15)
        )
        self.assertEqual(entered_roll["pitch_deviation_duration_seconds"], 2.0)
        self.assertEqual(entered_roll["roll_deviation_duration_seconds"], 0.0)
        self.assertEqual(result["pitch_deviation_duration_seconds"], 6.0)
        self.assertEqual(result["roll_deviation_duration_seconds"], 4.0)

    def test_hysteresis_prevents_threshold_chatter(self) -> None:
        self.engine.process(sample(timestamp=2_000, roll_deg=11))
        still_active = self.engine.process(sample(timestamp=3_000, roll_deg=9))
        neutral = self.engine.process(sample(timestamp=4_000, roll_deg=7))
        self.assertEqual(still_active["roll_status"], "moderate")
        self.assertEqual(neutral["roll_status"], "neutral")

    def test_pitch_sign_is_positive_forward_and_negative_backward(self) -> None:
        forward = self.engine.process(sample(timestamp=2_000, pitch_deg=15))
        backward = self.engine.process(sample(timestamp=3_000, pitch_deg=-15))
        self.assertGreater(forward["pitch_deviation_deg"], 0)
        self.assertLess(backward["pitch_deviation_deg"], 0)

    def test_pitch_keeps_direction_around_real_shirt_orientation(self) -> None:
        neutral = self.engine.process(
            {**sample(timestamp=2_000), "y": 15_500, "z": -3_900}
        )
        self.engine.calibrate("test-shirt", neutral)
        forward = self.engine.process(
            {**sample(timestamp=3_000), "y": 12_000, "z": -5_000}
        )
        backward = self.engine.process(
            {**sample(timestamp=4_000), "y": 15_500, "z": -2_000}
        )
        self.assertGreater(forward["pitch_deviation_deg"], 0)
        self.assertLess(backward["pitch_deviation_deg"], 0)

    def test_persisted_calibration_is_loaded_on_first_sample(self) -> None:
        engine = PostureEngine(
            lambda _: PROFILE,
            ema_alpha=1,
            hysteresis_deg=2,
            calibration_provider=lambda device_id, patient_id: (5.0, -3.0),
        )
        result = engine.process(sample(timestamp=1_000, pitch_deg=10, roll_deg=2))
        self.assertEqual(result["reference_pitch_deg"], 5.0)
        self.assertEqual(result["reference_roll_deg"], -3.0)
        self.assertAlmostEqual(result["pitch_deviation_deg"], 5.0, delta=0.1)
        self.assertAlmostEqual(result["roll_deviation_deg"], 5.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
