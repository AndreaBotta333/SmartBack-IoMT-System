"""Composizione dei servizi applicativi con gli adattatori correnti."""

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from app.repositories import (
    CalibrationRepository,
    DeviceRepository,
    IdentityRepository,
    NightSessionRepository,
    NotificationRepository,
    PatientRepository,
    PortalRepository,
    RuntimeRepository,
)
from app.services import (
    AuthService,
    CalibrationService,
    DayMonitoringService,
    DeviceService,
    NightMonitoringService,
    NotificationService,
    PatientAccessService,
    PatientService,
    PortalService,
)
from app.infrastructure.telemetry import TelemetryCoordinator


class ServiceContainer:
    """Crea casi d'uso aggiornati usando lo stato runtime corrente."""

    def __init__(
        self,
        *,
        database_provider: Callable[[], sqlite3.Connection | None],
        mqtt_provider: Callable[[], object | None],
        influx_provider: Callable[[], object | None],
        posture_engine_provider: Callable[[], object | None],
        database_path: str,
        database_lock: threading.RLock,
        password_hasher: Callable[..., tuple[str, str]],
        threshold_provider: Callable[[sqlite3.Row], Any],
        user_serializer: Callable[[sqlite3.Row], dict[str, Any]],
        device_connected: Callable[[str | None], bool],
        night_session_serializer: Callable[[sqlite3.Row], dict[str, Any]],
        notification_mapper: Callable[[dict[str, Any]], dict[str, Any] | None],
        notification_sender: Callable[[list[str], dict[str, Any]], int],
        notification_cooldown_seconds: float,
        notification_lock: asyncio.Lock,
        notification_last_processed: dict[tuple[str, str], float],
        pending_calibrations: dict[tuple[str, str], dict[str, Any]],
        stale_seconds: float,
        calibration_algorithm_version: int,
    ):
        self.database_provider = database_provider
        self.mqtt_provider = mqtt_provider
        self.influx_provider = influx_provider
        self.posture_engine_provider = posture_engine_provider
        self.database_path = database_path
        self.database_lock = database_lock
        self.password_hasher = password_hasher
        self.threshold_provider = threshold_provider
        self.user_serializer = user_serializer
        self.device_connected = device_connected
        self.night_session_serializer = night_session_serializer
        self.notification_mapper = notification_mapper
        self.notification_sender = notification_sender
        self.notification_cooldown_seconds = notification_cooldown_seconds
        self.notification_lock = notification_lock
        self.notification_last_processed = notification_last_processed
        self.pending_calibrations = pending_calibrations
        self.stale_seconds = stale_seconds
        self.calibration_algorithm_version = calibration_algorithm_version

    def database(self) -> sqlite3.Connection:
        database = self.database_provider()
        if database is None:
            raise RuntimeError("Database SmartBack non inizializzato")
        return database

    def auth(self) -> AuthService:
        return AuthService(
            IdentityRepository(self.database(), self.database_path),
            self.password_hasher,
        )

    def patient_access(self) -> PatientAccessService:
        return PatientAccessService(
            IdentityRepository(self.database(), self.database_path)
        )

    def calibration_repository(self) -> CalibrationRepository:
        return CalibrationRepository(self.database(), self.database_lock)

    def calibration(self) -> CalibrationService:
        return CalibrationService(
            self.calibration_repository(),
            mqtt=self.mqtt_provider(),
            influx=self.influx_provider(),
            posture_engine=self.posture_engine_provider(),
            stale_seconds=self.stale_seconds,
            algorithm_version=self.calibration_algorithm_version,
            threshold_provider=self.threshold_provider,
            pending_samples=self.pending_calibrations,
        )

    def notifications(self) -> NotificationService:
        return NotificationService(
            NotificationRepository(self.database(), self.database_lock),
            self.notification_mapper,
            self.notification_sender,
            self.notification_cooldown_seconds,
            self.notification_lock,
            self.notification_last_processed,
        )

    def night_monitoring(self) -> NightMonitoringService:
        return NightMonitoringService(
            NightSessionRepository(self.database(), self.database_lock),
            influx=self.influx_provider(),
            messaging=self.mqtt_provider(),
            serializer=self.night_session_serializer,
        )

    def day_monitoring(self) -> DayMonitoringService:
        return DayMonitoringService(
            self.influx_provider(),
            threshold_provider=self.threshold_provider,
            stale_seconds=self.stale_seconds,
        )

    def devices(self) -> DeviceService:
        return DeviceService(
            DeviceRepository(self.database(), self.database_lock),
            self.mqtt_provider(),
        )

    def patients(self) -> PatientService:
        return PatientService(
            PatientRepository(self.database(), self.database_lock),
            self.mqtt_provider(),
            self.password_hasher,
        )

    def portal(self) -> PortalService:
        return PortalService(
            PortalRepository(self.database()),
            self.user_serializer,
            self.device_connected,
        )

    def telemetry(self) -> TelemetryCoordinator:
        return TelemetryCoordinator(
            RuntimeRepository(self.database(), self.database_lock),
            self.stale_seconds,
        )
