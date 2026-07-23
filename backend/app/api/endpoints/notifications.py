"""Endpoint delle notifiche dell'app SmartBack."""

import sqlite3
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.schemas import PushTokenRequest
from app.services.notification_service import NotificationService


NotificationServiceProvider = Callable[[], NotificationService]


def register_notification_endpoints(
    router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: NotificationServiceProvider,
) -> dict[str, Callable]:
    """Registra le route e restituisce gli handler per la compatibilità interna."""

    @router.post("/api/v1/notifications/token", status_code=204)
    def register_push_token(
        body: PushTokenRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        service_provider().repository.register_token(str(user["id"]), body.token)

    @router.delete("/api/v1/notifications/token", status_code=204)
    def unregister_push_token(
        body: PushTokenRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        service_provider().repository.unregister_token(str(user["id"]), body.token)

    @router.get("/api/v1/notifications")
    def list_app_notifications(
        limit: int = 100,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        return {
            "items": service_provider().repository.list(str(user["id"]), limit)
        }

    @router.delete("/api/v1/notifications", status_code=204)
    def clear_app_notifications(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        service_provider().repository.clear(str(user["id"]))

    @router.post("/api/v1/notifications/test")
    async def test_push_notification(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        token_count, accepted = await service_provider().send_test(str(user["id"]))
        if token_count == 0:
            raise HTTPException(
                status_code=409,
                detail="Nessun dispositivo registrato per le notifiche",
            )
        if accepted == 0:
            raise HTTPException(
                status_code=502,
                detail="La notifica non è stata accettata dal servizio Expo",
            )
        return {"accepted": accepted}

    return {
        "register_push_token": register_push_token,
        "unregister_push_token": unregister_push_token,
        "list_app_notifications": list_app_notifications,
        "clear_app_notifications": clear_app_notifications,
        "test_push_notification": test_push_notification,
    }
