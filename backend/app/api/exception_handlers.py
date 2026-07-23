from dataclasses import dataclass
from functools import wraps
from typing import Type

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services import (
    AccountDeactivationFailed,
    DayArchiveUnavailable,
    DeviceAlreadyAssigned,
    DeviceAssignmentNotFound,
    DeviceClaimFailed,
    DeviceCreationFailed,
    DeviceInventoryNotFound,
    DeviceNotFound,
    EmailAlreadyRegistered,
    FiscalCodeAlreadyRegistered,
    IdentityConflict,
    InvalidCredentials,
    InvalidCurrentPassword,
    NightSessionNotFound,
    PatientAlreadyAssociated,
    PatientAssignedToAnotherDoctor,
    PatientAssociationFailed,
    PatientNotRegistered,
    ProtectedAccount,
)


@dataclass(frozen=True)
class ErrorResponse:
    status_code: int
    detail: str


APPLICATION_ERRORS: dict[Type[Exception], ErrorResponse] = {
    DayArchiveUnavailable: ErrorResponse(
        503,
        "Archivio temporale non disponibile",
    ),
    DeviceCreationFailed: ErrorResponse(
        409,
        "Impossibile generare la maglia di test",
    ),
    DeviceClaimFailed: ErrorResponse(
        409,
        "La maglia non è più disponibile o è già stata acquisita",
    ),
    DeviceNotFound: ErrorResponse(404, "Maglia non trovata"),
    DeviceInventoryNotFound: ErrorResponse(
        404,
        "Maglia non presente nell'inventario",
    ),
    DeviceAlreadyAssigned: ErrorResponse(
        409,
        "La maglia o il paziente possiedono già un'assegnazione attiva",
    ),
    DeviceAssignmentNotFound: ErrorResponse(
        404,
        "Assegnazione attiva non trovata",
    ),
    InvalidCredentials: ErrorResponse(401, "Email o password non corrette"),
    EmailAlreadyRegistered: ErrorResponse(409, "Utente già registrato"),
    FiscalCodeAlreadyRegistered: ErrorResponse(
        409,
        "Codice fiscale già associato a un account registrato",
    ),
    IdentityConflict: ErrorResponse(
        409,
        "Email o codice fiscale già registrato",
    ),
    InvalidCurrentPassword: ErrorResponse(
        400,
        "La password attuale non è corretta",
    ),
    ProtectedAccount: ErrorResponse(
        403,
        "L'account amministratore non può essere eliminato",
    ),
    AccountDeactivationFailed: ErrorResponse(
        500,
        "Impossibile eliminare l'account",
    ),
    NightSessionNotFound: ErrorResponse(
        404,
        "Sessione notturna non trovata",
    ),
    PatientAssignedToAnotherDoctor: ErrorResponse(
        409,
        "Impossibile aggiungere il paziente perché è già associato a un altro medico",
    ),
    PatientAlreadyAssociated: ErrorResponse(
        409,
        "Il paziente è già presente nella tua lista",
    ),
    PatientAssociationFailed: ErrorResponse(
        409,
        "Impossibile completare l'associazione del paziente",
    ),
    PatientNotRegistered: ErrorResponse(
        404,
        "Nessun paziente registrato con questo codice fiscale",
    ),
}


def register_application_exception_handlers(app: FastAPI) -> None:
    """Registra la traduzione applicazione -> HTTP in un solo punto."""

    for exception_type, response in APPLICATION_ERRORS.items():
        async def handler(
            _request: Request,
            _exception: Exception,
            mapped: ErrorResponse = response,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=mapped.status_code,
                content={"detail": mapped.detail},
            )

        app.add_exception_handler(exception_type, handler)


def translate_application_errors(function):
    """Adatta anche le invocazioni dirette dei controller al contratto HTTP."""

    @wraps(function)
    def translated(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except tuple(APPLICATION_ERRORS) as error:
            mapped = APPLICATION_ERRORS[type(error)]
            raise HTTPException(
                status_code=mapped.status_code,
                detail=mapped.detail,
            ) from None

    return translated
