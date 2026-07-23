"""Casi d'uso applicativi SmartBack."""

from app.services.device_service import (
    DeviceAlreadyAssigned,
    DeviceAssignmentNotFound,
    DeviceClaimFailed,
    DeviceCreationFailed,
    DeviceInventoryNotFound,
    DeviceNotFound,
    DeviceService,
)
from app.services.day_monitoring_service import (
    DayArchiveUnavailable,
    DayMonitoringService,
)
from app.services.patient_service import (
    PatientAlreadyAssociated,
    PatientAssignedToAnotherDoctor,
    PatientAssociationFailed,
    PatientNotRegistered,
    PatientService,
)
from app.services.portal_service import PortalService
from app.services.auth_service import (
    AccountDeactivationFailed,
    AuthService,
    EmailAlreadyRegistered,
    FiscalCodeAlreadyRegistered,
    IdentityConflict,
    InvalidCredentials,
    InvalidCurrentPassword,
    ProtectedAccount,
)
from app.services.patient_access_service import (
    PatientAccessDenied, PatientAccessService, PatientNotFound,
    PatientSelectionRequired,
)
from app.services.calibration_service import CalibrationConflict, CalibrationService
from app.services.notification_service import NotificationService
from app.services.night_monitoring_service import (
    NightMonitoringService,
    NightSessionConflict,
    NightSessionNotFound,
)

__all__ = [
    "DeviceAlreadyAssigned",
    "DayArchiveUnavailable",
    "DayMonitoringService",
    "DeviceAssignmentNotFound",
    "DeviceClaimFailed",
    "DeviceCreationFailed",
    "DeviceInventoryNotFound",
    "DeviceNotFound",
    "DeviceService",
    "PatientAlreadyAssociated",
    "PatientAssignedToAnotherDoctor",
    "PatientAssociationFailed",
    "PatientNotRegistered",
    "PatientService",
    "PortalService",
    "AuthService",
    "AccountDeactivationFailed",
    "EmailAlreadyRegistered",
    "FiscalCodeAlreadyRegistered",
    "IdentityConflict",
    "InvalidCredentials",
    "InvalidCurrentPassword",
    "ProtectedAccount",
    "PatientAccessDenied",
    "PatientAccessService",
    "PatientNotFound",
    "PatientSelectionRequired",
    "CalibrationConflict",
    "CalibrationService",
    "NotificationService",
    "NightMonitoringService",
    "NightSessionConflict",
    "NightSessionNotFound",
]
