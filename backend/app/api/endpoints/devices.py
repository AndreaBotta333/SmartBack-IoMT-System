"""Endpoint di inventario, stato e assegnazione delle smart shirt."""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.api.exception_handlers import translate_application_errors
from app.schemas import (
    DeviceAssignmentRequest,
    DeviceClaimRequest,
    DeviceCreateRequest,
)
from app.services.device_service import DeviceService


def register_device_endpoints(
    devices_router: APIRouter,
    grafana_router: APIRouter,
    service_provider: Callable[[], DeviceService],
    grafana_user_provider: Callable[[str | None], sqlite3.Row],
    patient_by_code_provider: Callable[[sqlite3.Row, str], sqlite3.Row],
    latest_device_provider: Callable[[], dict[str, Any] | None],
    current_user_provider: Callable,
    patient_device_status_provider: Callable[
        [sqlite3.Row, str | None], dict[str, Any]
    ],
) -> dict[str, Callable]:
    """Registra le API dispositivi mantenendo separato il runtime applicativo."""

    @devices_router.get("/api/v1/device/latest")
    def get_latest_device():
        latest = latest_device_provider()
        if latest is None:
            raise HTTPException(
                status_code=404,
                detail="Nessuno stato del dispositivo ancora ricevuto",
            )
        return latest

    @devices_router.get("/api/v1/device/status")
    def get_patient_device_status(
        patient_id: str | None = None,
        user: sqlite3.Row = Depends(current_user_provider),
    ):
        return patient_device_status_provider(user, patient_id)

    @grafana_router.post("/api/v1/grafana/devices", status_code=201)
    @translate_application_errors
    def grafana_create_device(
        body: DeviceCreateRequest,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        return service_provider().create_test_device(
            doctor_id=str(user["id"]),
            display_name=body.display_name,
        )

    @grafana_router.post(
        "/api/v1/grafana/devices/discovered/{device_id}/claim",
        status_code=201,
    )
    @translate_application_errors
    def grafana_claim_discovered_device(
        device_id: str,
        body: DeviceClaimRequest,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        return service_provider().claim_discovered_device(
            doctor_id=str(user["id"]),
            device_id=device_id,
            display_name=body.display_name,
        )

    @grafana_router.delete(
        "/api/v1/grafana/devices/{device_id}",
        status_code=204,
    )
    @translate_application_errors
    def grafana_remove_device(
        device_id: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        service_provider().remove_device(
            doctor_id=str(user["id"]),
            device_id=device_id,
        )
        return Response(status_code=204)

    @grafana_router.put("/api/v1/grafana/devices/{device_id}/assignment")
    @translate_application_errors
    def grafana_assign_device(
        device_id: str,
        body: DeviceAssignmentRequest,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        patient = patient_by_code_provider(user, body.patient_code)
        return service_provider().assign_device(
            doctor_id=str(user["id"]),
            device_id=device_id,
            patient_id=str(patient["id"]),
            patient_code=str(patient["patient_code"]),
        )

    @grafana_router.delete(
        "/api/v1/grafana/devices/{device_id}/assignment",
        status_code=204,
    )
    @translate_application_errors
    def grafana_release_device(
        device_id: str,
        smartback_grafana_session: str | None = Cookie(default=None),
    ):
        user = grafana_user_provider(smartback_grafana_session)
        service_provider().release_device(
            doctor_id=str(user["id"]),
            device_id=device_id,
        )
        return Response(status_code=204)

    return {
        "get_latest_device": get_latest_device,
        "get_patient_device_status": get_patient_device_status,
        "grafana_create_device": grafana_create_device,
        "grafana_claim_discovered_device": grafana_claim_discovered_device,
        "grafana_remove_device": grafana_remove_device,
        "grafana_assign_device": grafana_assign_device,
        "grafana_release_device": grafana_release_device,
    }
