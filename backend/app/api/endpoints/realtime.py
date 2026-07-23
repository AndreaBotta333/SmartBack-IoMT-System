"""Endpoint WebSocket per i dati posturali in tempo reale."""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.infrastructure.realtime import RealtimeConnectionManager


def register_realtime_endpoints(
    router: APIRouter,
    manager: RealtimeConnectionManager,
    session_user_provider: Callable[[str], sqlite3.Row | None],
    patient_access: Callable[[sqlite3.Row, str | None], sqlite3.Row],
    latest_posture_provider: Callable[[], dict[str, Any] | None],
) -> dict[str, Callable]:
    @router.websocket("/ws/wearable")
    async def wearable_stream(websocket: WebSocket):
        await websocket.accept()
        token = websocket.query_params.get("token")
        requested_patient_id = websocket.query_params.get("patient_id")
        user = session_user_provider(token) if token else None
        if user is None:
            await websocket.close(code=4401, reason="Sessione richiesta")
            return
        try:
            patient = patient_access(user, requested_patient_id)
        except HTTPException:
            await websocket.close(
                code=4403,
                reason="Paziente non autorizzato",
            )
            return
        patient_code = str(patient["patient_code"])
        manager.connect(websocket, patient_code)
        try:
            latest = latest_posture_provider()
            if (
                latest
                and str(latest.get("patient_id")) == patient_code
            ):
                await websocket.send_json(latest)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(websocket)

    return {"wearable_stream": wearable_stream}
