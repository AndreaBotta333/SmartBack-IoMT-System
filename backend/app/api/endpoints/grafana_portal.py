"""API del portale medico e dell'auth proxy Grafana."""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Response

from app.api.exception_handlers import translate_application_errors
from app.schemas import (
    AssociatePatientRequest,
    GrafanaLoginRequest,
    RegisterRequest,
)
from app.services import AuthService, PatientService, PortalService


def register_grafana_portal_endpoints(
    router: APIRouter,
    *,
    cookie_name: str,
    authenticate_grafana_user: Callable[[str, str], sqlite3.Row],
    auth_service_provider: Callable[[], AuthService],
    app_register: Callable[[RegisterRequest], dict[str, Any]],
    grafana_user_provider: Callable[[str | None], sqlite3.Row],
    portal_service_provider: Callable[[], PortalService],
    patient_service_provider: Callable[[], PatientService],
    patient_by_code: Callable[[sqlite3.Row, str], sqlite3.Row],
    user_serializer: Callable[[sqlite3.Row], dict[str, Any]],
    active_night_session: Callable[[str], sqlite3.Row | None],
) -> dict[str, Callable]:
    def set_session_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            cookie_name,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )

    @router.post("/api/v1/grafana/login")
    def grafana_login(body: GrafanaLoginRequest, response: Response):
        user = authenticate_grafana_user(body.email, body.password)
        if user["role"] != "doctor" or not bool(
            user["professional_verified"]
        ):
            raise HTTPException(
                status_code=403,
                detail="Accesso riservato ai medici verificati",
            )
        token = auth_service_provider().create_session(str(user["id"]))
        set_session_cookie(response, token)
        return {"status": "ok", "redirect": "/smartback/"}

    @router.post("/api/v1/grafana/register", status_code=201)
    def grafana_register_doctor(
        body: RegisterRequest,
        response: Response,
    ):
        if body.role != "doctor":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Da questa pagina è consentita soltanto "
                    "la registrazione medica"
                ),
            )
        registered = app_register(body)
        set_session_cookie(response, str(registered["access_token"]))
        return {"status": "ok", "redirect": "/smartback/"}

    @router.get("/api/v1/grafana/home")
    def grafana_home_data(
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        return portal_service_provider().home(user)

    @router.post("/api/v1/grafana/patients", status_code=201)
    @translate_application_errors
    def grafana_associate_patient(
        body: AssociatePatientRequest,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_service_provider().associate(
            doctor_id=str(user["id"]),
            fiscal_code=body.fiscal_code,
        )
        return user_serializer(patient)

    @router.delete(
        "/api/v1/grafana/patients/{patient_code}",
        status_code=204,
    )
    def grafana_remove_patient(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        patient_service_provider().remove(
            doctor_id=str(user["id"]),
            patient_id=str(patient["id"]),
        )
        return Response(status_code=204)

    @router.get("/api/v1/grafana/auth")
    def grafana_auth(
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        return Response(
            status_code=200,
            headers={
                "X-WEBAUTH-USER": user["email"],
                "X-WEBAUTH-NAME": user["name"],
                "X-WEBAUTH-ROLE": "Viewer",
            },
        )

    @router.post("/api/v1/grafana/token-rotation")
    def grafana_token_rotation(
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        grafana_user_provider(smartback_grafana_session)
        return {"status": "ok"}

    @router.get(
        "/api/v1/grafana/patients/{patient_code}/night-monitoring/status"
    )
    def grafana_night_monitoring_status(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        session = active_night_session(str(patient["id"]))
        return {
            "active": session is not None,
            "session_id": (
                str(session["id"]) if session is not None else None
            ),
        }

    @router.post("/api/v1/grafana/logout", status_code=204)
    def grafana_logout(
        response: Response,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        if smartback_grafana_session:
            auth_service_provider().logout(smartback_grafana_session)
        response.delete_cookie(cookie_name, path="/")
        response.headers["Clear-Site-Data"] = '"cookies"'
        response.headers["Cache-Control"] = "no-store"

    return {
        "grafana_login": grafana_login,
        "grafana_register_doctor": grafana_register_doctor,
        "grafana_home_data": grafana_home_data,
        "grafana_associate_patient": grafana_associate_patient,
        "grafana_remove_patient": grafana_remove_patient,
        "grafana_auth": grafana_auth,
        "grafana_token_rotation": grafana_token_rotation,
        "grafana_night_monitoring_status": grafana_night_monitoring_status,
        "grafana_logout": grafana_logout,
    }
