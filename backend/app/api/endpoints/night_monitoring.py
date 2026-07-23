"""Endpoint applicativi e Grafana del monitoraggio notturno."""

import sqlite3
from collections.abc import Callable
from functools import wraps

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.api.exception_handlers import translate_application_errors
from app.services.night_monitoring_service import (
    NightMonitoringService,
    NightSessionConflict,
)


def translate_night_conflicts(function):
    @wraps(function)
    def translated(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except NightSessionConflict as error:
            raise HTTPException(status_code=409, detail=error.detail) from None

    return translated


def register_night_monitoring_endpoints(
    router: APIRouter,
    grafana_router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: Callable[[], NightMonitoringService],
    patient_access: Callable[[sqlite3.Row, str | None], sqlite3.Row],
    patient_by_code: Callable[[sqlite3.Row, str], sqlite3.Row],
    grafana_user_provider: Callable[[str | None], sqlite3.Row],
) -> dict[str, Callable]:
    """Registra i casi d'uso notturni senza query o logica MQTT."""

    def require_patient(user: sqlite3.Row) -> None:
        if user["role"] != "patient":
            raise HTTPException(
                status_code=403,
                detail=(
                    "La modalità notturna può essere attivata o fermata "
                    "solo dal paziente"
                ),
            )

    @router.post("/api/v1/night-monitoring/start", status_code=201)
    @translate_night_conflicts
    def start_night_monitoring(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_patient(user)
        return service_provider().start(user, user)

    @router.post("/api/v1/night-monitoring/stop")
    @translate_night_conflicts
    def stop_night_monitoring(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_patient(user)
        return service_provider().stop(user, "patient")

    @router.get("/api/v1/night-monitoring/status")
    def night_monitoring_status(
        patient_id: str | None = None,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        return service_provider().status(patient)

    @router.get("/api/v1/night-monitoring/history")
    def night_monitoring_history(
        patient_id: str | None = None,
        limit: int = 50,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        return service_provider().history(patient, limit)

    @router.get("/api/v1/night-monitoring/history/summary")
    def night_monitoring_history_summary(
        patient_id: str | None = None,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        return service_provider().history_summary(patient)

    @router.get("/api/v1/night-monitoring/sessions/{session_id}")
    @translate_application_errors
    def night_monitoring_session(
        session_id: str,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        row, result = service_provider().session(session_id)
        patient_access(user, str(row["patient_id"]))
        return result

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/night-monitoring/start"
    )
    @translate_night_conflicts
    def grafana_start_night_monitoring(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        service_provider().start(patient, user)
        return RedirectResponse(
            url=(
                f"/api/v1/grafana/patients/{patient_code}"
                "/night-monitoring/control"
            ),
            status_code=303,
        )

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/night-monitoring/stop"
    )
    @translate_night_conflicts
    def grafana_stop_night_monitoring(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code(user, patient_code)
        service_provider().stop(patient, "doctor")
        return RedirectResponse(
            url=(
                f"/api/v1/grafana/patients/{patient_code}"
                "/night-monitoring/control"
            ),
            status_code=303,
        )

    return {
        "start_night_monitoring": start_night_monitoring,
        "stop_night_monitoring": stop_night_monitoring,
        "night_monitoring_status": night_monitoring_status,
        "night_monitoring_history": night_monitoring_history,
        "night_monitoring_history_summary": night_monitoring_history_summary,
        "night_monitoring_session": night_monitoring_session,
        "grafana_start_night_monitoring": grafana_start_night_monitoring,
        "grafana_stop_night_monitoring": grafana_stop_night_monitoring,
    }
