import asyncio
import unittest

from app import bootstrap as main_module


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class RealtimePatientRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_websockets = main_module.websockets
        self.simona_socket = FakeSocket()
        self.andrea_socket = FakeSocket()
        main_module.websockets = {
            self.simona_socket: "patient-simona",
            self.andrea_socket: "patient-andrea",
        }

    def tearDown(self) -> None:
        main_module.websockets = self.original_websockets

    def test_posture_is_sent_only_to_the_matching_patient(self) -> None:
        payload = {"patient_id": "patient-andrea", "pitch_deg": 12.0}

        asyncio.run(main_module.broadcast(payload))

        self.assertEqual(self.simona_socket.messages, [])
        self.assertEqual(self.andrea_socket.messages, [payload])

    def test_payload_without_patient_is_not_broadcast(self) -> None:
        asyncio.run(main_module.broadcast({"type": "unknown"}))

        self.assertEqual(self.simona_socket.messages, [])
        self.assertEqual(self.andrea_socket.messages, [])


if __name__ == "__main__":
    unittest.main()
