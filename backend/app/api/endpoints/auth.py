"""Endpoint di autenticazione e gestione dell'account SmartBack."""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.exception_handlers import translate_application_errors
from app.schemas import (
    AvatarRequest,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService


AuthServiceProvider = Callable[[], AuthService]
UserSerializer = Callable[[sqlite3.Row], dict[str, Any]]


def register_auth_endpoints(
    router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: AuthServiceProvider,
    user_serializer: UserSerializer,
) -> dict[str, Callable]:
    """Registra le route account e restituisce alias compatibili."""

    @router.post("/api/v1/auth/register", status_code=201)
    @translate_application_errors
    def register(body: RegisterRequest):
        service = service_provider()
        user = service.register(
            role=body.role,
            email=str(body.email),
            password=body.password,
            first_name=body.first_name,
            last_name=body.last_name,
            fiscal_code=body.fiscal_code,
        )
        return {
            "access_token": service.create_session(str(user["id"])),
            "user": user_serializer(user),
        }

    @router.post("/api/v1/auth/login")
    @translate_application_errors
    def login(body: LoginRequest):
        service = service_provider()
        user = service.authenticate(str(body.email), body.password)
        return {
            "access_token": service.create_session(str(user["id"])),
            "user": user_serializer(user),
        }

    @router.get("/api/v1/auth/me")
    def me(user: sqlite3.Row = Depends(current_user_dependency)):
        return user_serializer(user)

    @router.post("/api/v1/auth/logout", status_code=204)
    def logout(authorization: str | None = Header(default=None)):
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            service_provider().logout(token)

    @router.delete("/api/v1/auth/account", status_code=204)
    @translate_application_errors
    def delete_account(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        service_provider().deactivate_account(user)

    @router.put("/api/v1/auth/password", status_code=204)
    @translate_application_errors
    def change_password(
        body: ChangePasswordRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        service_provider().change_password(
            user,
            body.current_password,
            body.new_password,
        )

    @router.put("/api/v1/auth/avatar")
    def change_avatar(
        body: AvatarRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        updated = service_provider().change_avatar(
            str(user["id"]), body.avatar_data
        )
        return user_serializer(updated)

    return {
        "register": register,
        "login": login,
        "me": me,
        "logout": logout,
        "delete_account": delete_account,
        "change_password": change_password,
        "change_avatar": change_avatar,
    }
