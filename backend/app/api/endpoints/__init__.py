"""Registrazione degli endpoint, separata dal bootstrap dell'applicazione."""

from app.api.endpoints.auth import register_auth_endpoints
from app.api.endpoints.calibration import register_calibration_endpoints
from app.api.endpoints.doctor_patients import register_doctor_patient_endpoints
from app.api.endpoints.devices import register_device_endpoints
from app.api.endpoints.day_monitoring import (
    normalize_history_range,
    register_day_monitoring_endpoints,
)
from app.api.endpoints.notifications import register_notification_endpoints
from app.api.endpoints.night_monitoring import (
    register_night_monitoring_endpoints,
)
from app.api.endpoints.realtime import register_realtime_endpoints
from app.api.endpoints.system import register_system_endpoints
from app.api.endpoints.grafana_portal import (
    register_grafana_portal_endpoints,
)
from app.api.endpoints.grafana_pages import (
    register_grafana_page_endpoints,
)

__all__ = [
    "register_auth_endpoints",
    "register_calibration_endpoints",
    "register_doctor_patient_endpoints",
    "register_device_endpoints",
    "normalize_history_range",
    "register_day_monitoring_endpoints",
    "register_notification_endpoints",
    "register_night_monitoring_endpoints",
    "register_realtime_endpoints",
    "register_system_endpoints",
    "register_grafana_portal_endpoints",
    "register_grafana_page_endpoints",
]
