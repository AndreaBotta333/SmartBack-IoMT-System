"""Creazione e configurazione dell'applicazione FastAPI."""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.exception_handlers import (
    register_application_exception_handlers,
)
from app.api.routers import OPENAPI_SUMMARIES, OPENAPI_TAGS


def italian_validation_message(error: dict[str, Any]) -> str:
    error_type = str(error.get("type", ""))
    context = error.get("ctx") or {}
    location = error.get("loc") or ()
    field = str(location[-1]) if location else ""
    original = str(error.get("msg", ""))
    if error_type == "missing":
        return "Campo obbligatorio"
    if error_type == "string_too_short":
        return (
            "Il campo deve contenere almeno "
            f"{context.get('min_length')} caratteri"
        )
    if error_type == "string_too_long":
        return (
            "Il campo può contenere al massimo "
            f"{context.get('max_length')} caratteri"
        )
    if error_type in {"greater_than", "greater_than_equal"}:
        operator = (
            "maggiore di"
            if error_type == "greater_than"
            else "maggiore o uguale a"
        )
        return (
            f"Il valore deve essere {operator} "
            f"{context.get('gt', context.get('ge'))}"
        )
    if error_type in {"less_than", "less_than_equal"}:
        operator = (
            "minore di"
            if error_type == "less_than"
            else "minore o uguale a"
        )
        return (
            f"Il valore deve essere {operator} "
            f"{context.get('lt', context.get('le'))}"
        )
    if error_type in {"float_parsing", "int_parsing", "decimal_parsing"}:
        return "Inserisci un numero valido"
    if error_type in {
        "string_pattern_mismatch",
        "literal_error",
        "enum",
    }:
        return "Valore non consentito"
    if field == "email" or field.endswith("email"):
        return "Indirizzo email non valido"
    if error_type == "value_error":
        custom = re.sub(r"^Value error,\s*", "", original)
        return custom if custom else "Valore non valido"
    return "Valore non valido"


async def italian_request_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {
                    "loc": list(error.get("loc", ())),
                    "type": error.get("type", "validation_error"),
                    "msg": italian_validation_message(error),
                }
                for error in exc.errors()
            ]
        },
    )


def create_application(
    *,
    lifespan,
    routers: Iterable[APIRouter],
    static_directory: Path,
) -> FastAPI:
    app = FastAPI(
        title="SmartBack API",
        version="0.1.0",
        description=(
            "API del sistema SmartBack per app, portale medico, "
            "monitoraggio e smart shirt."
        ),
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )
    register_application_exception_handlers(app)
    app.add_exception_handler(
        RequestValidationError,
        italian_request_validation_error,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount(
        "/smartback-static",
        StaticFiles(directory=static_directory),
        name="smartback-static",
    )
    for router in routers:
        app.include_router(router)

    def italian_openapi_schema() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=OPENAPI_TAGS,
        )
        for (method, path), summary in OPENAPI_SUMMARIES.items():
            operation = schema.get("paths", {}).get(path, {}).get(method)
            if operation is not None:
                operation["summary"] = summary
        app.openapi_schema = schema
        return schema

    app.openapi = italian_openapi_schema
    return app
