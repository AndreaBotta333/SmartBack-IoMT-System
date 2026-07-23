"""Endpoint diagnostici e informativi del servizio."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter


def register_system_endpoints(
    router: APIRouter,
    health_provider: Callable[[], dict[str, Any]],
) -> dict[str, Callable]:
    @router.get("/")
    def root():
        return {
            "service": "SmartBack API",
            "docs": "/docs",
            "health": "/health",
        }

    @router.get("/health")
    def health():
        return health_provider()

    return {"root": root, "health": health}
