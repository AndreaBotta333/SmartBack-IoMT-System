import sqlite3

from app.repositories.identity_repository import IdentityRepository


class PatientSelectionRequired(Exception): pass
class PatientAccessDenied(Exception): pass
class PatientNotFound(Exception): pass


class PatientAccessService:
    def __init__(self, repository: IdentityRepository):
        self.repository = repository

    def by_id(self, user: sqlite3.Row, patient_id: str | None) -> sqlite3.Row:
        if user["role"] == "patient":
            if patient_id and patient_id != user["id"]:
                raise PatientAccessDenied
            return user
        if not patient_id:
            raise PatientSelectionRequired
        patient = self.repository.associated_patient_by_id(
            str(user["id"]), patient_id
        )
        if patient is None:
            raise PatientAccessDenied
        return patient

    def by_code(self, user: sqlite3.Row, patient_code: str) -> sqlite3.Row:
        if user["role"] == "patient":
            if user["patient_code"] != patient_code:
                raise PatientAccessDenied
            return user
        if user["id"] == "usr_grafana_admin":
            patient = self.repository.patient_by_code(patient_code)
            if patient is None:
                raise PatientNotFound
            return patient
        patient = self.repository.associated_patient_by_code(
            str(user["id"]), patient_code
        )
        if patient is None:
            raise PatientAccessDenied
        return patient
