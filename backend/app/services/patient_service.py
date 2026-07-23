"""Casi d'uso per anagrafica e associazione medico-paziente."""

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from app.repositories.patient_repository import PatientRepository


class PatientAssignedToAnotherDoctor(Exception):
    pass


class PatientAlreadyAssociated(Exception):
    pass


class PatientAssociationFailed(Exception):
    pass


class PatientNotRegistered(Exception):
    pass


class PatientService:
    def __init__(
        self,
        repository: PatientRepository,
        messaging: object | None,
        password_hasher: Callable[[str], tuple[str, str]],
    ):
        self.repository = repository
        self.messaging = messaging
        self.password_hasher = password_hasher

    def associate(self, doctor_id: str, fiscal_code: str) -> sqlite3.Row:
        patient = self.repository.by_fiscal_code(fiscal_code)
        if patient is None:
            patient_id = f"usr_{secrets.token_hex(8)}"
            digest, salt = self.password_hasher(secrets.token_urlsafe(32))
            patient = self.repository.create_pending(
                (
                    patient_id, "Utente non registrato", "Utente", "non registrato",
                    f"pending-{secrets.token_hex(12)}@smartback.local", digest, salt,
                    "patient", datetime.now(timezone.utc).isoformat(),
                    f"patient-{patient_id.removeprefix('usr_')}", fiscal_code, 0,
                )
            )
        links = self.repository.doctor_links(str(patient["id"]))
        if any(str(row["doctor_id"]) != doctor_id for row in links):
            raise PatientAssignedToAnotherDoctor
        if links:
            raise PatientAlreadyAssociated
        try:
            self.repository.add_to_doctor(doctor_id, str(patient["id"]))
        except sqlite3.IntegrityError as error:
            self.repository.database.rollback()
            raise PatientAssociationFailed from error
        return patient

    def associate_existing(
        self, doctor_id: str, fiscal_code: str
    ) -> sqlite3.Row:
        """Associa dall'app un paziente già presente nell'anagrafica."""
        patient = self.repository.by_fiscal_code(fiscal_code)
        if patient is None:
            raise PatientNotRegistered
        links = self.repository.doctor_links(str(patient["id"]))
        if any(str(row["doctor_id"]) != doctor_id for row in links):
            raise PatientAssignedToAnotherDoctor
        if links:
            raise PatientAlreadyAssociated
        try:
            self.repository.add_to_doctor(doctor_id, str(patient["id"]))
        except sqlite3.IntegrityError as error:
            self.repository.database.rollback()
            raise PatientAssociationFailed from error
        return patient

    def list_for_doctor(self, doctor_id: str) -> list[sqlite3.Row]:
        return self.repository.list_for_doctor(doctor_id)

    def save_monitoring_config(
        self,
        *,
        patient_id: str,
        updated_by: str,
        moderate_deviation_deg: float,
        marked_deviation_deg: float,
        moderate_roll_deg: float,
        marked_roll_deg: float,
        persistence_seconds: float,
    ) -> None:
        self.repository.save_monitoring_config(
            patient_id=patient_id,
            moderate_deviation_deg=moderate_deviation_deg,
            marked_deviation_deg=marked_deviation_deg,
            moderate_roll_deg=moderate_roll_deg,
            marked_roll_deg=marked_roll_deg,
            persistence_seconds=persistence_seconds,
            updated_by=updated_by,
        )

    def reset_monitoring_config(self, patient_id: str) -> None:
        self.repository.delete_monitoring_config(patient_id)

    def remove(self, doctor_id: str, patient_id: str) -> None:
        assignments = self.repository.remove_from_doctor(doctor_id, patient_id)
        if self.messaging is None:
            return
        for assignment in assignments:
            device_id = str(assignment["device_id"])
            self.messaging.publish_device_assignment(device_id, None)
            if assignment["source_type"] == "simulated":
                self.messaging.publish_simulated_device(device_id, active=False)
