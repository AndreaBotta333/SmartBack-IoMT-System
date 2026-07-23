"""Casi d'uso dell'inventario e delle assegnazioni delle maglie."""

from datetime import datetime, timezone
from typing import Protocol

from app.repositories.device_repository import (
    DeviceRepository,
    RepositoryConflict,
)


class DeviceMessaging(Protocol):
    def publish_device_assignment(
        self,
        device_id: str,
        patient_id: str | None,
    ) -> None: ...

    def publish_simulated_device(
        self,
        device_id: str,
        *,
        active: bool,
    ) -> None: ...


class DeviceNotFound(Exception):
    pass


class DeviceCreationFailed(Exception):
    pass


class DeviceClaimFailed(Exception):
    pass


class DeviceInventoryNotFound(Exception):
    pass


class DeviceAlreadyAssigned(Exception):
    pass


class DeviceAssignmentNotFound(Exception):
    pass


class DeviceService:
    def __init__(
        self,
        repository: DeviceRepository,
        messaging: DeviceMessaging | None = None,
    ) -> None:
        self._repository = repository
        self._messaging = messaging

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_test_device(
        self,
        *,
        doctor_id: str,
        display_name: str,
    ) -> dict[str, object]:
        try:
            device = self._repository.create_simulated(
                doctor_id=doctor_id,
                display_name=display_name,
                created_at=self._now(),
            )
        except RepositoryConflict:
            raise DeviceCreationFailed from None
        if self._messaging:
            self._messaging.publish_simulated_device(
                str(device["device_id"]),
                active=False,
            )
        return {**device, "has_telemetry": False}

    def claim_discovered_device(
        self,
        *,
        doctor_id: str,
        device_id: str,
        display_name: str,
    ) -> dict[str, object]:
        device = self._repository.claim_discovered(
            doctor_id=doctor_id,
            device_id=device_id,
            display_name=display_name,
        )
        if device is None:
            raise DeviceClaimFailed
        return {**device, "has_telemetry": True}

    def assign_device(
        self,
        *,
        doctor_id: str,
        device_id: str,
        patient_id: str,
        patient_code: str,
    ) -> dict[str, str]:
        assigned_at = self._now()
        try:
            self._repository.assign(
                doctor_id=doctor_id,
                device_id=device_id,
                patient_id=patient_id,
                assigned_at=assigned_at,
            )
        except LookupError:
            raise DeviceInventoryNotFound from None
        except RepositoryConflict:
            raise DeviceAlreadyAssigned from None
        device = self._repository.owned_device(
            doctor_id=doctor_id,
            device_id=device_id,
        )
        if self._messaging:
            self._messaging.publish_device_assignment(device_id, patient_code)
            if device["source_type"] == "simulated":
                self._messaging.publish_simulated_device(
                    device_id,
                    active=True,
                )
        return {
            "device_id": device_id,
            "patient_code": patient_code,
            "assigned_at": assigned_at,
        }

    def release_device(
        self,
        *,
        doctor_id: str,
        device_id: str,
    ) -> None:
        assignment = self._repository.release(
            doctor_id=doctor_id,
            device_id=device_id,
            released_at=self._now(),
        )
        if assignment is None:
            raise DeviceAssignmentNotFound
        if self._messaging:
            self._messaging.publish_device_assignment(device_id, None)
            if assignment["source_type"] == "simulated":
                self._messaging.publish_simulated_device(
                    device_id,
                    active=False,
                )

    def remove_device(
        self,
        *,
        doctor_id: str,
        device_id: str,
    ) -> None:
        device = self._repository.remove(
            doctor_id=doctor_id,
            device_id=device_id,
            removed_at=self._now(),
        )
        if device is None:
            raise DeviceNotFound
        if self._messaging:
            self._messaging.publish_device_assignment(device_id, None)
            if device["source_type"] == "simulated":
                self._messaging.publish_simulated_device(
                    device_id,
                    active=False,
                )
