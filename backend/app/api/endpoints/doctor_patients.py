"""Endpoint dell'app dedicati ai pazienti seguiti dal medico."""

import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.exception_handlers import translate_application_errors
from app.schemas import AssociatePatientRequest, MonitoringConfigRequest
from app.services.patient_service import PatientService


def register_doctor_patient_endpoints(
    router: APIRouter,
    current_user_dependency: Callable[..., sqlite3.Row],
    service_provider: Callable[[], PatientService],
    patient_access: Callable[[sqlite3.Row, str | None], sqlite3.Row],
    user_serializer: Callable[[sqlite3.Row], dict[str, Any]],
    monitoring_config_provider: Callable[[sqlite3.Row], dict[str, float]],
    latest_patient_code_provider: Callable[[], str | None],
    night_session_provider: Callable[[str], sqlite3.Row | None],
) -> dict[str, Callable]:
    """Registra le API medico-paziente senza dipendere dal runtime globale."""

    def require_doctor(user: sqlite3.Row, detail: str) -> None:
        if user["role"] != "doctor":
            raise HTTPException(status_code=403, detail=detail)

    @router.get("/api/v1/doctor/patients")
    def doctor_patients(
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_doctor(
            user,
            "Accesso riservato a medici e fisioterapisti",
        )
        rows = service_provider().list_for_doctor(str(user["id"]))
        current_patient_code = latest_patient_code_provider()
        items = [
            {
                **user_serializer(row),
                "associated_at": row["associated_at"],
                "night_mode_active": bool(row["night_mode_active"]),
                "has_live_data": (
                    row["patient_code"] == current_patient_code
                    or bool(row["night_mode_active"])
                ),
            }
            for row in rows
        ]
        return {"items": items, "count": len(items)}

    @router.post("/api/v1/doctor/patients", status_code=201)
    @translate_application_errors
    def associate_patient(
        body: AssociatePatientRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_doctor(
            user,
            "Accesso riservato a medici e fisioterapisti",
        )
        patient = service_provider().associate_existing(
            str(user["id"]), body.fiscal_code
        )
        night_active = night_session_provider(str(patient["id"])) is not None
        return {
            **user_serializer(patient),
            "night_mode_active": night_active,
            "has_live_data": (
                patient["patient_code"] == latest_patient_code_provider()
                or night_active
            ),
        }

    @router.get("/api/v1/doctor/patients/{patient_id}/monitoring-config")
    def get_monitoring_config(
        patient_id: str,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_doctor(user, "Accesso riservato al medico")
        patient = patient_access(user, patient_id)
        return monitoring_config_provider(patient)

    @router.put("/api/v1/doctor/patients/{patient_id}/monitoring-config")
    def update_monitoring_config(
        patient_id: str,
        body: MonitoringConfigRequest,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_doctor(user, "Accesso riservato al medico")
        patient = patient_access(user, patient_id)
        service_provider().save_monitoring_config(
            patient_id=str(patient["id"]),
            updated_by=str(user["id"]),
            moderate_deviation_deg=body.moderate_deviation_deg,
            marked_deviation_deg=body.marked_deviation_deg,
            moderate_roll_deg=body.moderate_roll_deg,
            marked_roll_deg=body.marked_roll_deg,
            persistence_seconds=body.persistence_seconds,
        )
        return monitoring_config_provider(patient)

    @router.delete("/api/v1/doctor/patients/{patient_id}/monitoring-config")
    def reset_monitoring_config(
        patient_id: str,
        user: sqlite3.Row = Depends(current_user_dependency),
    ):
        require_doctor(user, "Accesso riservato al medico")
        patient = patient_access(user, patient_id)
        service_provider().reset_monitoring_config(str(patient["id"]))
        return monitoring_config_provider(patient)

    return {
        "doctor_patients": doctor_patients,
        "associate_patient": associate_patient,
        "get_monitoring_config": get_monitoring_config,
        "update_monitoring_config": update_monitoring_config,
        "reset_monitoring_config": reset_monitoring_config,
    }
