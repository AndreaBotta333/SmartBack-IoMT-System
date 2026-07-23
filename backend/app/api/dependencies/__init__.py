"""Dipendenze FastAPI condivise dai diversi domini API."""

from app.api.dependencies.auth import (
    build_current_user_dependency,
    require_grafana_user,
)

__all__ = ["build_current_user_dependency", "require_grafana_user"]
