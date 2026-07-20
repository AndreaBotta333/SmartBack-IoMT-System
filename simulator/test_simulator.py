import random
import unittest

from simulator import (
    Pose,
    accgyro_payload,
    battery_payload,
    dataloss_payload,
    gravity_vector,
    pose_at,
)


class SmartShirtSimulatorTests(unittest.TestCase):
    def test_accgyro_contract_matches_esp_gateway(self) -> None:
        payload = accgyro_payload(
            elapsed_ms=1234,
            sample_number=32,
            pose=Pose("neutral", 0, 0),
            rng=random.Random(1),
        )
        self.assertEqual(
            set(payload),
            {
                "type",
                "timestamp",
                "samplenum",
                "sampling_frequency",
                "orientation",
                "samples",
            },
        )
        self.assertEqual(payload["type"], "accgyro")
        self.assertEqual(len(payload["samples"]), 16)
        self.assertTrue(
            all(set(sample) == {"x", "y", "z"} for sample in payload["samples"])
        )

    def test_pitch_and_roll_axes_keep_their_sign(self) -> None:
        _, _, forward_z = gravity_vector(15, 0)
        _, _, backward_z = gravity_vector(-15, 0)
        right_x, _, _ = gravity_vector(0, 15)
        left_x, _, _ = gravity_vector(0, -15)
        self.assertLess(forward_z, 0)
        self.assertGreater(backward_z, 0)
        self.assertGreater(right_x, 0)
        self.assertLess(left_x, 0)

    def test_day_cycle_contains_all_daytime_directions(self) -> None:
        names = {pose_at(second).name for second in range(0, 100, 4)}
        self.assertTrue({"neutral", "forward", "backward", "right"} <= names)

    def test_battery_contract_matches_esp_gateway(self) -> None:
        payload = battery_payload(96)
        self.assertEqual(payload["type"], "battery")
        self.assertEqual(payload["state_of_charge"], 96)
        self.assertIn("remaining_capacity", payload)

    def test_dataloss_contract_matches_esp_gateway(self) -> None:
        self.assertEqual(dataloss_payload(), {"type": "dataloss", "value": 1})

    def test_samples_fit_the_esp_signed_16_bit_contract(self) -> None:
        payload = accgyro_payload(
            elapsed_ms=0,
            sample_number=0,
            pose=Pose("extreme", 90, 90),
            rng=random.Random(2),
        )
        self.assertTrue(
            all(
                -32768 <= value <= 32767
                for sample in payload["samples"]
                for value in sample.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
