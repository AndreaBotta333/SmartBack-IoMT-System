"""Endpoint del monitoraggio posturale diurno."""

import math
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.exception_handlers import translate_application_errors
from app.services.day_monitoring_service import DayMonitoringService


def normalize_history_range(
    *,
    minutes: int,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime, int]:
    """Normalizza i parametri HTTP mantenendo il contratto storico esistente."""
    requested_end = end or datetime.now(timezone.utc)
    if requested_end.tzinfo is None:
        requested_end = requested_end.replace(tzinfo=timezone.utc)
    requested_end = requested_end.astimezone(timezone.utc)
    if start is None:
        normalized_minutes = min(max(minutes, 1), 527_040)
        requested_start = requested_end - timedelta(
            minutes=normalized_minutes
        )
    else:
        requested_start = (
            start.replace(tzinfo=timezone.utc)
            if start.tzinfo is None
            else start.astimezone(timezone.utc)
        )
        normalized_minutes = max(
            1,
            math.ceil(
                (requested_end - requested_start).total_seconds() / 60
            ),
        )
    if requested_start >= requested_end:
        raise HTTPException(
            status_code=422,
            detail="L'inizio dello storico deve precedere la fine",
        )
    if requested_end - requested_start > timedelta(days=366):
        raise HTTPException(
            status_code=422,
            detail="L'intervallo massimo consultabile e di 366 giorni",
        )
    return requested_start, requested_end, normalized_minutes


def register_day_monitoring_endpoints(
    router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: Callable[[], DayMonitoringService],
    patient_access: Callable[[sqlite3.Row, str | None], sqlite3.Row],
    latest_posture_provider: Callable[[], dict[str, Any] | None],
) -> dict[str, Callable]:
    """Registra le API diurne senza accoppiarle a InfluxDB o MQTT."""

    @router.get("/api/v1/posture/latest")
    def get_latest_posture():
        latest = latest_posture_provider()
        if latest is None:
            raise HTTPException(
                status_code=404,
                detail="Nessun campione posturale ancora ricevuto",
            )
        return latest

    @router.get("/api/v1/posture/history")
    @translate_application_errors
    def posture_history(
        minutes: int = 60,
        patient_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 600,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        requested_start, requested_end, normalized_minutes = (
            normalize_history_range(
                minutes=minutes,
                start=start,
                end=end,
            )
        )
        return service_provider().history(
            patient,
            start=requested_start,
            end=requested_end,
            minutes=normalized_minutes,
            limit=limit,
        )

    @router.get("/api/v1/posture/history/availability")
    @translate_application_errors
    def posture_history_availability(
        patient_id: str | None = None,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        return service_provider().availability(patient)

    @router.get("/api/v1/posture/history/sessions")
    @translate_application_errors
    def posture_history_sessions(
        patient_id: str | None = None,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        patient = patient_access(user, patient_id)
        return service_provider().sessions(patient)

    @router.get("/api/v1/patient/statistics")
    @translate_application_errors
    def patient_statistics(
        minutes: int = 60,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        if user["role"] != "patient":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Le statistiche personali sono riservate al paziente"
                ),
            )
        return service_provider().statistics(user, minutes)

    return {
        "get_latest_posture": get_latest_posture,
        "posture_history": posture_history,
        "posture_history_availability": posture_history_availability,
        "posture_history_sessions": posture_history_sessions,
        "patient_statistics": patient_statistics,
    }
