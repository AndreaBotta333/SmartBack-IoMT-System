"""Coordinamento tra MQTT e persistenza runtime."""

from datetime import datetime, timedelta, timezone
import sqlite3

from app.repositories.runtime_repository import RuntimeRepository


class TelemetryCoordinator:
    def __init__(
        self, repository: RuntimeRepository, stale_seconds: float
    ) -> None:
        self.repository = repository
        self.stale_seconds = stale_seconds

    def register_seen_device(self, device_id: str, quality: str) -> None:
        self.repository.register_seen_device(device_id, quality)

    def active_assignments(self) -> list[dict[str, str]]:
        return self.repository.active_assignments()

    def simulated_device_ids(self) -> list[str]:
        return self.repository.simulated_device_ids()

    def active_simulated_night_device_ids(self) -> list[str]:
        return self.repository.active_simulated_night_device_ids()

    def active_night_session_for_sample(
        self, device_id: str, patient_code: str
    ) -> dict[str, str] | None:
        return self.repository.active_night_session_for_sample(
            device_id, patient_code
        )

    def active_night_sessions(self) -> list[dict[str, str]]:
        return self.repository.active_night_sessions()

    def monitoring_config(self, patient_id: str) -> sqlite3.Row | None:
        return self.repository.monitoring_config(patient_id)

    def patient_by_code(self, patient_code: str) -> sqlite3.Row | None:
        return self.repository.patient_by_code(patient_code)

    def update_night_summary(
        self,
        session_id: str,
        position: str,
        elapsed_seconds: float,
        changed: bool,
    ) -> None:
        self.repository.update_night_summary(
            session_id, position, elapsed_seconds, changed
        )

    def is_connected(
        self,
        last_seen_at: str | None,
        *,
        now: datetime | None = None,
    ) -> bool:
        if not last_seen_at:
            return False
        try:
            last_seen = datetime.fromisoformat(
                last_seen_at.replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            return False
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        return timedelta(0) <= reference - last_seen <= timedelta(
            seconds=self.stale_seconds
        )
