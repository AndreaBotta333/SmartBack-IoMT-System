"""Contratti HTTP del backend SmartBack."""

from app.schemas.requests import (
    AssociatePatientRequest,
    AvatarRequest,
    CalibrationConfirmation,
    ChangePasswordRequest,
    DeviceAssignmentRequest,
    DeviceClaimRequest,
    DeviceCreateRequest,
    GrafanaLoginRequest,
    LoginRequest,
    ManualCalibrationRequest,
    MonitoringConfigRequest,
    PushTokenRequest,
    RegisterRequest,
)
from app.schemas.device_messages import (
    NormalizedDeviceStatus,
    NormalizedPostureSample,
)

__all__ = [
    "AssociatePatientRequest",
    "AvatarRequest",
    "CalibrationConfirmation",
    "ChangePasswordRequest",
    "DeviceAssignmentRequest",
    "DeviceClaimRequest",
    "DeviceCreateRequest",
    "GrafanaLoginRequest",
    "LoginRequest",
    "ManualCalibrationRequest",
    "MonitoringConfigRequest",
    "PushTokenRequest",
    "RegisterRequest",
    "NormalizedDeviceStatus",
    "NormalizedPostureSample",
]
