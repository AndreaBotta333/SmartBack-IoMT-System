"""Gestione tecnica delle connessioni WebSocket attive."""

from collections.abc import Callable
from typing import Any

from fastapi import WebSocket


class RealtimeConnectionManager:
    def __init__(
        self,
        connection_store_provider: Callable[[], dict[WebSocket, str]],
    ):
        self.connection_store_provider = connection_store_provider

    def connect(self, websocket: WebSocket, patient_code: str) -> None:
        self.connection_store_provider()[websocket] = patient_code

    def disconnect(self, websocket: WebSocket) -> None:
        self.connection_store_provider().pop(websocket, None)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        payload_patient = str(payload.get("patient_id") or "")
        for socket, patient_code in list(
            self.connection_store_provider().items()
        ):
            if not payload_patient or payload_patient != patient_code:
                continue
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(socket)
