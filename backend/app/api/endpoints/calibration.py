"""Endpoint della calibrazione posturale live e manuale."""

import sqlite3
from collections.abc import Callable
from functools import wraps

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.schemas import CalibrationConfirmation, ManualCalibrationRequest
from app.services.calibration_service import (
    CalibrationConflict,
    CalibrationService,
)


def translate_calibration_conflicts(function):
    """Mantiene il dettaglio specifico prodotto dal caso d'uso."""

    @wraps(function)
    def translated(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CalibrationConflict as error:
            raise HTTPException(status_code=409, detail=error.detail) from None

    return translated


def register_calibration_endpoints(
    devices_router: APIRouter,
    grafana_router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: Callable[[], CalibrationService],
    grafana_user_provider: Callable[[str | None], sqlite3.Row],
    patient_by_code_provider: Callable[[sqlite3.Row, str], sqlite3.Row],
    engine_available_provider: Callable[[], bool],
    latest_patient_code_provider: Callable[[], str],
) -> dict[str, Callable]:
    """Registra le API di calibrazione senza accoppiarle a MQTT o SQLite."""

    @devices_router.post("/api/v1/devices/{device_id}/calibration")
    @translate_calibration_conflicts
    def calibrate(
        device_id: str,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        if not engine_available_provider():
            raise HTTPException(
                status_code=503,
                detail="Motore posturale non disponibile",
            )
        service = service_provider()
        sample = service.fresh_sample(
            latest_patient_code_provider(),
            device_id,
        )
        patient_code = str(sample["patient_id"])
        patient = patient_by_code_provider(user, patient_code)
        return service.calibrate(
            patient=patient,
            calibrated_by=user,
            patient_code=patient_code,
            device_id=device_id,
        )

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/calibration"
    )
    @translate_calibration_conflicts
    def grafana_calibrate_patient(
        patient_code: str,
        body: CalibrationConfirmation,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        if not body.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Conferma esplicita richiesta prima di modificare "
                    "la calibrazione"
                ),
            )
        patient = patient_by_code_provider(user, patient_code)
        return service_provider().calibrate(
            patient=patient,
            calibrated_by=user,
            patient_code=patient_code,
        )

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/calibration-snapshot",
        status_code=204,
    )
    @translate_calibration_conflicts
    def grafana_capture_calibration_sample(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient_by_code_provider(user, patient_code)
        service_provider().capture(str(user["id"]), patient_code)
        return Response(status_code=204)

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/calibration-form",
        status_code=204,
    )
    @translate_calibration_conflicts
    def grafana_calibrate_patient_form(
        patient_code: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code_provider(user, patient_code)
        service = service_provider()
        sample = service.consume_capture(str(user["id"]), patient_code)
        service.calibrate(
            patient=patient,
            calibrated_by=user,
            patient_code=patient_code,
            captured_sample=sample,
        )
        return Response(status_code=204)

    @grafana_router.post(
        "/api/v1/grafana/patients/{patient_code}/manual-calibration"
    )
    @translate_calibration_conflicts
    def grafana_manual_calibration(
        patient_code: str,
        body: ManualCalibrationRequest,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code_provider(user, patient_code)
        return service_provider().manual(
            patient=patient,
            calibrated_by=user,
            patient_code=patient_code,
            pitch_deg=body.pitch_deg,
            roll_deg=body.roll_deg,
        )

    return {
        "calibrate": calibrate,
        "grafana_calibrate_patient": grafana_calibrate_patient,
        "grafana_capture_calibration_sample": (
            grafana_capture_calibration_sample
        ),
        "grafana_calibrate_patient_form": grafana_calibrate_patient_form,
        "grafana_manual_calibration": grafana_manual_calibration,
    }
