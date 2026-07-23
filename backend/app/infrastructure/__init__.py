"""Adattatori tecnici condivisi dal runtime SmartBack."""

from app.infrastructure.lifecycle import (
    RuntimeComponents,
    RuntimeConfig,
    create_runtime_lifespan,
)
from app.infrastructure.realtime import RealtimeConnectionManager
from app.infrastructure.telemetry import TelemetryCoordinator

__all__ = [
    "RealtimeConnectionManager",
    "TelemetryCoordinator",
    "RuntimeComponents",
    "RuntimeConfig",
    "create_runtime_lifespan",
]
