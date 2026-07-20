import unittest

from app.night_service import NightPositionEngine


class NightPositionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persisted = []
        self.updates = []
        self.session = {"id": "night-test", "patient_id": "patient-1", "device_id": "shirt-1"}
        self.engine = NightPositionEngine(
            session_provider=lambda device, patient: self.session,
            summary_updater=lambda session, position, elapsed, changed: self.updates.append(
                (session, position, elapsed, changed)
            ),
            persister=self.persisted.append,
            ema_alpha=1,
            persistence_seconds=1,
            gap_seconds=5,
        )

    @staticmethod
    def sample(timestamp: int, x: float, y: float, z: float):
        return {
            "timestamp": timestamp,
            "device_id": "shirt-1",
            "patient_id": "patient-code-1",
            "x": x,
            "y": y,
            "z": z,
        }

    def test_prone_and_supine_require_a_stable_candidate(self) -> None:
        first = self.engine.process(self.sample(1_000, 0, 0, -1))
        stable = self.engine.process(self.sample(2_000, 0, 0, -1))
        self.engine.process(self.sample(3_000, 0, 0, -1))
        candidate = self.engine.process(self.sample(4_000, 0, 0, 1))
        supine = self.engine.process(self.sample(5_000, 0, 0, 1))

        self.assertEqual(first["position"], "unknown")
        self.assertEqual(stable["position"], "prone")
        self.assertEqual(candidate["position"], "prone")
        self.assertEqual(supine["position"], "supine")
        self.assertTrue(any(update[1] == "prone" for update in self.updates))

    def test_right_and_left_side_follow_lateral_axis(self) -> None:
        self.engine.process(self.sample(1_000, 1, 0, 0))
        right = self.engine.process(self.sample(2_000, 1, 0, 0))
        self.engine.process(self.sample(3_000, -1, 0, 0))
        left = self.engine.process(self.sample(4_000, -1, 0, 0))
        self.assertEqual(right["position"], "right_side")
        self.assertEqual(left["position"], "left_side")

    def test_upright_or_ambiguous_orientation_is_unknown(self) -> None:
        self.engine.process(self.sample(1_000, 0, 1, 0))
        result = self.engine.process(self.sample(2_000, 0, 1, 0))
        self.assertEqual(result["position"], "unknown")

    def test_long_silence_is_recorded_as_data_gap(self) -> None:
        self.engine.process(self.sample(1_000, 0, 0, -1))
        result = self.engine.process(self.sample(11_000, 0, 0, -1))
        self.assertEqual(result["data_gap_seconds"], 10)
        self.assertTrue(any(update[1] == "data_gap" for update in self.updates))

    def test_samples_without_active_session_are_ignored(self) -> None:
        engine = NightPositionEngine(
            session_provider=lambda device, patient: None,
            summary_updater=lambda *args: None,
            persister=self.persisted.append,
        )
        self.assertIsNone(engine.process(self.sample(1_000, 0, 0, -1)))
        self.assertEqual(self.persisted, [])


if __name__ == "__main__":
    unittest.main()
