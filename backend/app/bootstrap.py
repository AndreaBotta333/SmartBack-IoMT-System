"""Composizione finale e bootstrap compatibile dell'applicazione SmartBack.

Il modulo collega configurazione, infrastrutture, servizi ed endpoint, mantenendo
gli alias pubblici richiesti dai test e dai client esistenti. L'entrypoint ASGI
rimane nel modulo pubblico ``main``.
"""

import asyncio
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Response, WebSocket
from app.config import (
    ALERT_TOPIC, AUTH_DB_PATH, DATA_STALE_SECONDS, DEVICE_TOPIC,
    GRAFANA_ADMIN_PASSWORD, GRAFANA_ADMIN_USER, INFLUX_BUCKET,
    INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL, MARKED_DEVIATION_DEG,
    MARKED_ROLL_DEG, MEDICAL_REGISTRATION_CODE, MODERATE_DEVIATION_DEG,
    MODERATE_ROLL_DEG, MQTT_HOST, MQTT_PORT, PERSISTENCE_SECONDS,
    POSTURE_EMA_ALPHA, POSTURE_HYSTERESIS_DEG, POSTURE_TOPIC,
)
from app.api.routers import (
    auth_router,
    day_monitoring_router,
    devices_router,
    doctor_router,
    grafana_pages_router,
    grafana_router,
    night_monitoring_router,
    realtime_router,
    system_router,
)
from app.api.application import (
    create_application,
    italian_validation_message,
)
from app.api.dependencies import (
    build_current_user_dependency,
    require_grafana_user,
)
from app.api.endpoints import (
    register_auth_endpoints,
    register_calibration_endpoints,
    normalize_history_range,
    register_day_monitoring_endpoints,
    register_device_endpoints,
    register_doctor_patient_endpoints,
    register_notification_endpoints,
    register_night_monitoring_endpoints,
    register_realtime_endpoints,
    register_system_endpoints,
    register_grafana_portal_endpoints,
    register_grafana_page_endpoints,
)
from app.composition import ServiceContainer
from app.infrastructure import (
    RealtimeConnectionManager,
    RuntimeComponents,
    RuntimeConfig,
    create_runtime_lifespan,
)
from app.domain.night import NightPositionEngine
from app.domain.posture import PostureEngine, ThresholdProfile
from app.infrastructure.influx import InfluxManager
from app.infrastructure.mqtt import SmartBackMqttHandler
from app.infrastructure.push import notification_for_alert, send_expo_push
from app.repositories import CalibrationRepository
from app.schemas import (
    AssociatePatientRequest,
    DeviceAssignmentRequest,
    DeviceClaimRequest,
    DeviceCreateRequest,
    GrafanaLoginRequest,
    ManualCalibrationRequest,
    RegisterRequest,
)
from app.services import (
    DeviceService,
    PatientService,
    PortalService,
    AuthService,
    InvalidCredentials,
    PatientAccessDenied,
    PatientAccessService,
    PatientNotFound,
    PatientSelectionRequired,
    CalibrationService,
    DayMonitoringService,
    NotificationService,
    NightMonitoringService,
    NightSessionConflict,
)
from app.security import hash_password
from app.serializers import serialize_night_session, serialize_public_user
GRAFANA_SESSION_COOKIE = "smartback_grafana_session"
CALIBRATION_ALGORITHM_VERSION = 2

websockets: dict[WebSocket, str] = {}
realtime_manager = RealtimeConnectionManager(lambda: websockets)
influx_manager: InfluxManager | None = None
posture_engine: PostureEngine | None = None
mqtt_handler: SmartBackMqttHandler | None = None
night_engine: NightPositionEngine | None = None
auth_db: sqlite3.Connection | None = None
pending_grafana_calibrations: dict[tuple[str, str], dict[str, Any]] = {}
database_lock = threading.RLock()
push_delivery_lock = asyncio.Lock()
push_last_processed_at: dict[tuple[str, str], float] = {}
PUSH_NOTIFICATION_COOLDOWN_SECONDS = 60.0

services = ServiceContainer(
    database_provider=lambda: auth_db,
    mqtt_provider=lambda: mqtt_handler,
    influx_provider=lambda: influx_manager,
    posture_engine_provider=lambda: posture_engine,
    database_path=AUTH_DB_PATH,
    database_lock=database_lock,
    password_hasher=hash_password,
    threshold_provider=lambda patient: threshold_profile_for_patient(patient),
    user_serializer=lambda user: public_user(user),
    device_connected=lambda last_seen: device_is_connected(last_seen),
    night_session_serializer=serialize_night_session,
    notification_mapper=notification_for_alert,
    notification_sender=send_expo_push,
    notification_cooldown_seconds=PUSH_NOTIFICATION_COOLDOWN_SECONDS,
    notification_lock=push_delivery_lock,
    notification_last_processed=push_last_processed_at,
    pending_calibrations=pending_grafana_calibrations,
    stale_seconds=DATA_STALE_SECONDS,
    calibration_algorithm_version=CALIBRATION_ALGORITHM_VERSION,
)


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    return serialize_public_user(row)


def current_auth_service() -> AuthService:
    return services.auth()


def current_patient_access_service() -> PatientAccessService:
    return services.patient_access()


def current_calibration_repository() -> CalibrationRepository:
    return services.calibration_repository()


def current_calibration_service() -> CalibrationService:
    return services.calibration()


def current_notification_service() -> NotificationService:
    return services.notifications()


def current_night_monitoring_service() -> NightMonitoringService:
    return services.night_monitoring()


def current_day_monitoring_service() -> DayMonitoringService:
    return services.day_monitoring()


def user_for_session(token: str) -> sqlite3.Row | None:
    return current_auth_service().user_for_session(token)


def authenticate_user(email: str, password: str) -> sqlite3.Row:
    try:
        return current_auth_service().authenticate(email, password)
    except InvalidCredentials:
        raise HTTPException(status_code=401, detail="Email o password non corrette")


def ensure_grafana_admin() -> None:
    current_auth_service().ensure_grafana_admin(GRAFANA_ADMIN_PASSWORD)


def authenticate_grafana_user(identifier: str, password: str) -> sqlite3.Row:
    normalized = identifier.lower().strip()
    email = (
        "admin@smartback.local"
        if normalized == GRAFANA_ADMIN_USER.lower().strip()
        else normalized
    )
    return authenticate_user(email, password)


current_user = build_current_user_dependency(lambda token: user_for_session(token))


def threshold_profile_for_patient(patient: sqlite3.Row | None) -> ThresholdProfile:
    if patient is None:
        return ThresholdProfile(
            pitch_moderate_deg=MODERATE_DEVIATION_DEG,
            pitch_marked_deg=MARKED_DEVIATION_DEG,
            roll_moderate_deg=MODERATE_ROLL_DEG,
            roll_marked_deg=MARKED_ROLL_DEG,
            persistence_seconds=PERSISTENCE_SECONDS,
        )
    row = services.telemetry().monitoring_config(str(patient["id"]))
    return ThresholdProfile(
        pitch_moderate_deg=float(row["moderate_deviation_deg"]) if row else MODERATE_DEVIATION_DEG,
        pitch_marked_deg=float(row["marked_deviation_deg"]) if row else MARKED_DEVIATION_DEG,
        roll_moderate_deg=(
            float(row["moderate_roll_deg"])
            if row and row["moderate_roll_deg"] is not None
            else MODERATE_ROLL_DEG
        ),
        roll_marked_deg=(
            float(row["marked_roll_deg"])
            if row and row["marked_roll_deg"] is not None
            else MARKED_ROLL_DEG
        ),
        persistence_seconds=float(row["persistence_seconds"]) if row else PERSISTENCE_SECONDS,
    )


def monitoring_config_for_patient(patient: sqlite3.Row) -> dict[str, float]:
    return threshold_profile_for_patient(patient).as_dict()


def threshold_profile_for_patient_code(patient_code: str) -> ThresholdProfile:
    patient = services.telemetry().patient_by_code(patient_code)
    return threshold_profile_for_patient(patient)


def accessible_patient(user: sqlite3.Row, patient_id: str | None = None) -> sqlite3.Row:
    try:
        return current_patient_access_service().by_id(user, patient_id)
    except PatientSelectionRequired:
        raise HTTPException(status_code=400, detail="Seleziona un paziente")
    except PatientAccessDenied:
        if user["role"] == "patient":
            raise HTTPException(
                status_code=403,
                detail="Non puoi visualizzare i dati di un altro paziente",
            )
        raise HTTPException(status_code=403, detail="Paziente non associato al medico")


def accessible_patient_by_code(user: sqlite3.Row, patient_code: str) -> sqlite3.Row:
    try:
        return current_patient_access_service().by_code(user, patient_code)
    except PatientNotFound:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    except PatientAccessDenied:
        if user["role"] == "patient":
            raise HTTPException(
                status_code=403, detail="Non puoi calibrare un altro paziente"
            )
        raise HTTPException(status_code=403, detail="Paziente non associato al medico")


def stored_calibration_for_device(
    device_id: str, patient_code: str
) -> tuple[float, float] | None:
    row = current_calibration_repository().stored_reference(
        device_id, patient_code, CALIBRATION_ALGORITHM_VERSION
    )
    if row is None:
        return None
    return float(row["reference_pitch_deg"]), float(row["reference_roll_deg"])


async def broadcast(payload: dict[str, Any]) -> None:
    await realtime_manager.broadcast(payload)


def register_seen_device(device_id: str, quality: str) -> None:
    if auth_db is None:
        return
    services.telemetry().register_seen_device(device_id, quality)


def device_is_connected(
    last_seen_at: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    if auth_db is None:
        return False
    return services.telemetry().is_connected(last_seen_at, now=now)


def active_device_assignments() -> list[dict[str, str]]:
    if auth_db is None:
        return []
    return services.telemetry().active_assignments()


def patient_device_status(
    user: sqlite3.Row,
    patient_id: str | None,
) -> dict[str, Any]:
    if auth_db is None:
        raise HTTPException(status_code=503, detail="Database non disponibile")
    if user["role"] == "patient":
        patient = user
    else:
        if not patient_id:
            raise HTTPException(status_code=400, detail="Seleziona un paziente")
        patient = accessible_patient(user, patient_id)
    return current_device_service().patient_status(str(patient["id"]))


def simulated_device_ids() -> list[str]:
    if auth_db is None:
        return []
    return services.telemetry().simulated_device_ids()


def active_simulated_night_device_ids() -> list[str]:
    if auth_db is None:
        return []
    return services.telemetry().active_simulated_night_device_ids()


def active_night_session_for_sample(
    device_id: str, patient_code: str
) -> dict[str, str] | None:
    if auth_db is None:
        return None
    return services.telemetry().active_night_session_for_sample(
        device_id, patient_code
    )


def update_night_summary(
    session_id: str, position: str, elapsed_seconds: float, changed: bool
) -> None:
    if auth_db is None or elapsed_seconds <= 0:
        return
    services.telemetry().update_night_summary(
        session_id, position, elapsed_seconds, changed
    )


def bind_runtime_database(database: sqlite3.Connection) -> None:
    global auth_db
    auth_db = database


def bind_runtime_components(components: RuntimeComponents) -> None:
    global mqtt_handler, influx_manager, posture_engine, night_engine
    mqtt_handler = components.mqtt
    influx_manager = components.influx
    posture_engine = components.posture_engine
    night_engine = components.night_engine


lifespan = create_runtime_lifespan(
    RuntimeConfig(
        auth_db_path=AUTH_DB_PATH,
        influx_url=INFLUX_URL,
        influx_token=INFLUX_TOKEN,
        influx_org=INFLUX_ORG,
        influx_bucket=INFLUX_BUCKET,
        mqtt_host=MQTT_HOST,
        mqtt_port=MQTT_PORT,
        posture_topic=POSTURE_TOPIC,
        device_topic=DEVICE_TOPIC,
        alert_topic=ALERT_TOPIC,
        stale_seconds=DATA_STALE_SECONDS,
        posture_ema_alpha=POSTURE_EMA_ALPHA,
        posture_hysteresis_deg=POSTURE_HYSTERESIS_DEG,
    ),
    bind_database=bind_runtime_database,
    bind_components=bind_runtime_components,
    ensure_admin=ensure_grafana_admin,
    threshold_provider=threshold_profile_for_patient_code,
    calibration_provider=stored_calibration_for_device,
    night_session_provider=active_night_session_for_sample,
    night_summary_updater=update_night_summary,
    broadcast=broadcast,
    device_seen=register_seen_device,
    assignment_provider=active_device_assignments,
    simulated_device_provider=simulated_device_ids,
    active_night_simulation_provider=active_simulated_night_device_ids,
    active_night_sessions_provider=lambda: (
        services.telemetry().active_night_sessions()
    ),
    alert_dispatcher=lambda payload: (
        current_notification_service().dispatch(payload)
    ),
)


def system_health_snapshot() -> dict[str, Any]:
    mqtt_connected = bool(mqtt_handler and mqtt_handler.connected)
    influx_ready = bool(influx_manager and influx_manager.is_ready())
    latest_posture = mqtt_handler.latest_posture if mqtt_handler else None
    return {
        "status": "ok" if mqtt_connected and influx_ready else "degraded",
        "mqtt": mqtt_connected,
        "influxdb": influx_ready,
        "has_posture_data": latest_posture is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


_system_handlers = register_system_endpoints(
    system_router,
    system_health_snapshot,
)
root = _system_handlers["root"]
health = _system_handlers["health"]


_auth_handlers = register_auth_endpoints(
    auth_router,
    current_user,
    current_auth_service,
    public_user,
)
register = _auth_handlers["register"]
login = _auth_handlers["login"]


def verified_grafana_user(smartback_grafana_session: str | None) -> sqlite3.Row:
    return require_grafana_user(
        smartback_grafana_session,
        lambda token: user_for_session(token),
    )


def current_device_service() -> DeviceService:
    return services.devices()


def current_patient_service() -> PatientService:
    return services.patients()


def current_portal_service() -> PortalService:
    return services.portal()


def medical_portal_data(user: sqlite3.Row) -> dict[str, Any]:
    return current_portal_service().home(user)


_grafana_portal_handlers = register_grafana_portal_endpoints(
    grafana_router,
    cookie_name=GRAFANA_SESSION_COOKIE,
    authenticate_grafana_user=lambda identifier, password: (
        authenticate_grafana_user(identifier, password)
    ),
    auth_service_provider=lambda: current_auth_service(),
    app_register=lambda body: register(body),
    grafana_user_provider=lambda token: verified_grafana_user(token),
    portal_service_provider=lambda: current_portal_service(),
    patient_service_provider=lambda: current_patient_service(),
    patient_by_code=lambda user, patient_code: accessible_patient_by_code(
        user,
        patient_code,
    ),
    user_serializer=public_user,
    active_night_session=lambda patient_id: active_night_session(patient_id),
)
grafana_login = _grafana_portal_handlers["grafana_login"]
grafana_register_doctor = _grafana_portal_handlers[
    "grafana_register_doctor"
]
grafana_home_data = _grafana_portal_handlers["grafana_home_data"]
grafana_associate_patient = _grafana_portal_handlers[
    "grafana_associate_patient"
]
grafana_remove_patient = _grafana_portal_handlers[
    "grafana_remove_patient"
]
grafana_auth = _grafana_portal_handlers["grafana_auth"]
grafana_token_rotation = _grafana_portal_handlers[
    "grafana_token_rotation"
]
grafana_night_monitoring_status = _grafana_portal_handlers[
    "grafana_night_monitoring_status"
]
grafana_logout = _grafana_portal_handlers["grafana_logout"]


_device_handlers = register_device_endpoints(
    devices_router,
    grafana_router,
    lambda: current_device_service(),
    lambda token: verified_grafana_user(token),
    lambda user, patient_code: accessible_patient_by_code(user, patient_code),
    lambda: mqtt_handler.latest_device if mqtt_handler else None,
    current_user,
    patient_device_status,
)
get_latest_device = _device_handlers["get_latest_device"]
get_patient_device_status = _device_handlers["get_patient_device_status"]
grafana_create_device = _device_handlers["grafana_create_device"]
grafana_claim_discovered_device = _device_handlers[
    "grafana_claim_discovered_device"
]
grafana_remove_device = _device_handlers["grafana_remove_device"]
grafana_assign_device = _device_handlers["grafana_assign_device"]
grafana_release_device = _device_handlers["grafana_release_device"]


_calibration_handlers = register_calibration_endpoints(
    devices_router,
    grafana_router,
    current_user,
    lambda: current_calibration_service(),
    lambda token: verified_grafana_user(token),
    lambda user, patient_code: accessible_patient_by_code(user, patient_code),
    lambda: mqtt_handler is not None,
    lambda: (
        str(mqtt_handler.latest_posture.get("patient_id"))
        if mqtt_handler and mqtt_handler.latest_posture
        else ""
    ),
)
calibrate = _calibration_handlers["calibrate"]
grafana_calibrate_patient = _calibration_handlers[
    "grafana_calibrate_patient"
]
grafana_capture_calibration_sample = _calibration_handlers[
    "grafana_capture_calibration_sample"
]
grafana_calibrate_patient_form = _calibration_handlers[
    "grafana_calibrate_patient_form"
]
grafana_manual_calibration = _calibration_handlers[
    "grafana_manual_calibration"
]


_night_monitoring_handlers = register_night_monitoring_endpoints(
    night_monitoring_router,
    grafana_router,
    current_user,
    lambda: current_night_monitoring_service(),
    lambda user, patient_id: accessible_patient(user, patient_id),
    lambda user, patient_code: accessible_patient_by_code(user, patient_code),
    lambda token: verified_grafana_user(token),
)
grafana_start_night_monitoring = _night_monitoring_handlers[
    "grafana_start_night_monitoring"
]
grafana_stop_night_monitoring = _night_monitoring_handlers[
    "grafana_stop_night_monitoring"
]


_grafana_page_handlers = register_grafana_page_endpoints(
    grafana_pages_router,
    cookie_name=GRAFANA_SESSION_COOKIE,
    logo_candidates=(
        Path("/app/assets/smartback-logo-transparent.png"),
        Path(__file__).resolve().parents[2]
        / "mobile"
        / "app"
        / "assets"
        / "smartback-logo-transparent.png",
    ),
    calibration_algorithm_version=CALIBRATION_ALGORITHM_VERSION,
    grafana_user_provider=lambda token: verified_grafana_user(token),
    patient_by_code=lambda user, patient_code: accessible_patient_by_code(
        user,
        patient_code,
    ),
    calibration_repository_provider=lambda: (
        current_calibration_repository()
    ),
    day_sessions_provider=lambda patient_code: (
        influx_manager.query_day_sessions(patient_code)
        if influx_manager
        else []
    ),
    night_service_provider=lambda: current_night_monitoring_service(),
    auth_service_provider=lambda: current_auth_service(),
)
grafana_login_page = _grafana_page_handlers["grafana_login_page"]
smartback_logo = _grafana_page_handlers["smartback_logo"]
medical_portal_page = _grafana_page_handlers["medical_portal_page"]
grafana_calibration_control = _grafana_page_handlers[
    "grafana_calibration_control"
]
grafana_alert_session_control = _grafana_page_handlers[
    "grafana_alert_session_control"
]
grafana_night_monitoring_control = _grafana_page_handlers[
    "grafana_night_monitoring_control"
]
grafana_night_session_control = _grafana_page_handlers[
    "grafana_night_session_control"
]
grafana_calibration_page = _grafana_page_handlers[
    "grafana_calibration_page"
]
grafana_browser_logout = _grafana_page_handlers[
    "grafana_browser_logout"
]


me = _auth_handlers["me"]
logout = _auth_handlers["logout"]


_notification_handlers = register_notification_endpoints(
    auth_router,
    current_user,
    current_notification_service,
)
register_push_token = _notification_handlers["register_push_token"]
unregister_push_token = _notification_handlers["unregister_push_token"]
list_app_notifications = _notification_handlers["list_app_notifications"]
clear_app_notifications = _notification_handlers["clear_app_notifications"]
test_push_notification = _notification_handlers["test_push_notification"]


delete_account = _auth_handlers["delete_account"]
change_password = _auth_handlers["change_password"]
change_avatar = _auth_handlers["change_avatar"]


_doctor_patient_handlers = register_doctor_patient_endpoints(
    doctor_router,
    current_user,
    current_patient_service,
    accessible_patient,
    public_user,
    monitoring_config_for_patient,
    lambda: (
        str(mqtt_handler.latest_posture.get("patient_id"))
        if mqtt_handler and mqtt_handler.latest_posture
        else None
    ),
    lambda patient_id: active_night_session(patient_id),
)
doctor_patients = _doctor_patient_handlers["doctor_patients"]
associate_patient = _doctor_patient_handlers["associate_patient"]


_day_monitoring_handlers = register_day_monitoring_endpoints(
    day_monitoring_router,
    current_user,
    lambda: current_day_monitoring_service(),
    lambda user, patient_id: accessible_patient(user, patient_id),
    lambda: mqtt_handler.latest_posture if mqtt_handler else None,
)
get_latest_posture = _day_monitoring_handlers["get_latest_posture"]


def active_night_session(patient_id: str) -> sqlite3.Row | None:
    return current_night_monitoring_service().active(patient_id)


def _start_night_session(patient: sqlite3.Row, actor: sqlite3.Row) -> dict[str, Any]:
    try:
        return current_night_monitoring_service().start(patient, actor)
    except NightSessionConflict as error:
        raise HTTPException(status_code=409, detail=error.detail) from None


start_night_monitoring = _night_monitoring_handlers[
    "start_night_monitoring"
]
stop_night_monitoring = _night_monitoring_handlers["stop_night_monitoring"]
night_monitoring_status = _night_monitoring_handlers[
    "night_monitoring_status"
]
night_monitoring_history = _night_monitoring_handlers[
    "night_monitoring_history"
]
night_monitoring_history_summary = _night_monitoring_handlers[
    "night_monitoring_history_summary"
]
night_monitoring_session = _night_monitoring_handlers[
    "night_monitoring_session"
]


posture_history = _day_monitoring_handlers["posture_history"]
posture_history_availability = _day_monitoring_handlers[
    "posture_history_availability"
]
posture_history_sessions = _day_monitoring_handlers[
    "posture_history_sessions"
]
patient_statistics = _day_monitoring_handlers["patient_statistics"]


get_monitoring_config = _doctor_patient_handlers["get_monitoring_config"]
update_monitoring_config = _doctor_patient_handlers["update_monitoring_config"]
reset_monitoring_config = _doctor_patient_handlers["reset_monitoring_config"]


_realtime_handlers = register_realtime_endpoints(
    realtime_router,
    realtime_manager,
    lambda token: user_for_session(token),
    lambda user, patient_id: accessible_patient(user, patient_id),
    lambda: mqtt_handler.latest_posture if mqtt_handler else None,
)
wearable_stream = _realtime_handlers["wearable_stream"]


app = create_application(
    lifespan=lifespan,
    routers=(
        system_router,
        auth_router,
        doctor_router,
        day_monitoring_router,
        night_monitoring_router,
        devices_router,
        grafana_router,
        grafana_pages_router,
        realtime_router,
    ),
    static_directory=Path(__file__).parent / "presentation" / "static",
)
