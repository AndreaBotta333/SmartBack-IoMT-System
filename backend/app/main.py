import asyncio
import base64
import binascii
import hashlib
import hmac
import html
import math
import re
import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import (
    ALERT_TOPIC, AUTH_DB_PATH, DATA_STALE_SECONDS, DEVICE_TOPIC,
    GRAFANA_ADMIN_PASSWORD, GRAFANA_ADMIN_USER, INFLUX_BUCKET,
    INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL, MARKED_DEVIATION_DEG,
    MARKED_ROLL_DEG, MEDICAL_REGISTRATION_CODE, MODERATE_DEVIATION_DEG,
    MODERATE_ROLL_DEG, MQTT_HOST, MQTT_PORT, PERSISTENCE_SECONDS,
    POSTURE_EMA_ALPHA, POSTURE_HYSTERESIS_DEG, POSTURE_TOPIC,
)
from app.api.routers import (
    OPENAPI_TAGS,
    OPENAPI_SUMMARIES,
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
from app.database import init_database
from app.influx_manager import InfluxManager
from app.mqtt_handler import SmartBackMqttHandler
from app.night_service import NightPositionEngine
from app.posture_service import PostureEngine, ThresholdProfile
EMAIL_DOMAIN_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)
GRAFANA_SESSION_COOKIE = "smartback_grafana_session"
CALIBRATION_ALGORITHM_VERSION = 2

websockets: dict[WebSocket, str] = {}
influx_manager: InfluxManager | None = None
posture_engine: PostureEngine | None = None
mqtt_handler: SmartBackMqttHandler | None = None
night_engine: NightPositionEngine | None = None
auth_db: sqlite3.Connection | None = None
pending_grafana_calibrations: dict[tuple[str, str], dict[str, Any]] = {}
database_lock = threading.RLock()


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=2, max_length=50)
    last_name: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str
    fiscal_code: str | None = Field(default=None, max_length=16)
    medical_code: str | None = Field(default=None, max_length=80)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Nome e cognome sono entrambi obbligatori")
        if not re.fullmatch(r"[^\W\d_]+(?:[ '\u2019-][^\W\d_]+)*", normalized, re.UNICODE):
            raise ValueError("Nome e cognome possono contenere solo lettere, spazi e apostrofi")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email_domain(cls, value: EmailStr) -> EmailStr:
        if not EMAIL_DOMAIN_PATTERN.fullmatch(str(value)):
            raise ValueError("L'email deve avere il formato nome@provider.dominio")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"\d", value) or not re.search(r"[^\w\s]", value, re.UNICODE):
            raise ValueError("La password deve contenere almeno un numero e un simbolo speciale")
        return value

    @model_validator(mode="after")
    def validate_role_fields(self):
        self.role = self.role.strip().lower()
        if self.role == "patient":
            if not self.fiscal_code or not is_valid_fiscal_code(self.fiscal_code):
                raise ValueError("Codice fiscale non valido")
            self.fiscal_code = self.fiscal_code.upper().replace(" ", "")
            self.medical_code = None
        elif self.role == "doctor":
            if not self.medical_code or not hmac.compare_digest(self.medical_code.strip(), MEDICAL_REGISTRATION_CODE):
                raise ValueError("Codice medico non valido")
            self.fiscal_code = None
            self.medical_code = None
        else:
            raise ValueError("Ruolo non valido")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GrafanaLoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str


class CalibrationConfirmation(BaseModel):
    confirmed: bool


class ManualCalibrationRequest(BaseModel):
    pitch_deg: float | None = Field(default=None, ge=-180, le=180)
    roll_deg: float | None = Field(default=None, ge=-90, le=90)

    @model_validator(mode="after")
    def require_axis(self):
        if self.pitch_deg is None and self.roll_deg is None:
            raise ValueError("Inserisci almeno un valore di calibrazione")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not re.search(r"\d", value) or not re.search(r"[^\w\s]", value, re.UNICODE):
            raise ValueError("La nuova password deve contenere almeno un numero e un simbolo speciale")
        return value

    @model_validator(mode="after")
    def validate_password_difference(self):
        if self.current_password == self.new_password:
            raise ValueError("La nuova password deve essere diversa da quella attuale")
        return self


class AvatarRequest(BaseModel):
    avatar_data: str = Field(min_length=32, max_length=3_000_000)

    @field_validator("avatar_data")
    @classmethod
    def validate_avatar(cls, value: str) -> str:
        prefixes = ("data:image/jpeg;base64,", "data:image/png;base64,")
        prefix = next((candidate for candidate in prefixes if value.startswith(candidate)), None)
        if prefix is None:
            raise ValueError("La foto deve essere in formato JPEG o PNG")
        try:
            decoded = base64.b64decode(value[len(prefix):], validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("La foto selezionata non è valida") from None
        if len(decoded) > 2_000_000:
            raise ValueError("La foto è troppo grande; scegli un'immagine inferiore a 2 MB")
        return value


class AssociatePatientRequest(BaseModel):
    fiscal_code: str = Field(min_length=16, max_length=16)

    @field_validator("fiscal_code")
    @classmethod
    def validate_fiscal_code(cls, value: str) -> str:
        normalized = value.upper().replace(" ", "")
        if not is_valid_fiscal_code(normalized):
            raise ValueError("Codice fiscale non valido")
        return normalized


class DeviceAssignmentRequest(BaseModel):
    patient_code: str = Field(min_length=1, max_length=128)


class DeviceCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return " ".join(value.strip().split())


class DeviceClaimRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return " ".join(value.strip().split())

class MonitoringConfigRequest(BaseModel):
    moderate_deviation_deg: float = Field(ge=1, le=45)
    marked_deviation_deg: float = Field(ge=2, le=60)
    moderate_roll_deg: float = Field(default=10, ge=1, le=45)
    marked_roll_deg: float = Field(default=20, ge=2, le=60)
    persistence_seconds: float = Field(ge=1, le=300)

    @model_validator(mode="after")
    def validate_threshold_order(self):
        if self.marked_deviation_deg <= self.moderate_deviation_deg:
            raise ValueError("La soglia pitch marcata deve essere maggiore della soglia pitch moderata")
        if self.marked_roll_deg <= self.moderate_roll_deg:
            raise ValueError("La soglia roll marcata deve essere maggiore della soglia roll moderata")
        return self


def is_valid_fiscal_code(value: str) -> bool:
    code = value.upper().replace(" ", "")
    pattern = r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$"
    if not re.fullmatch(pattern, code):
        return False
    odd_values = {
        **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
        **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23])),
    }
    even_values = {**{str(index): index for index in range(10)}, **{letter: index for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}}
    total = sum(odd_values[char] if index % 2 == 0 else even_values[char] for index, char in enumerate(code[:15]))
    return code[15] == chr(ord("A") + total % 26)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 310_000)
    return digest.hex(), actual_salt.hex()


def public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "email": row["email"],
        "first_name": row["first_name"], "last_name": row["last_name"],
        "role": row["role"], "patient_code": row["patient_code"],
        "fiscal_code": row["fiscal_code"] if "fiscal_code" in row.keys() else None,
        "professional_verified": bool(row["professional_verified"]),
        "account_registered": bool(row["account_registered"]),
        "avatar_data": row["avatar_data"],
    }


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    auth_db.execute(
        "INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now(timezone.utc).isoformat()),
    )
    auth_db.commit()
    return token


def user_for_session(token: str) -> sqlite3.Row | None:
    # Il gateway può eseguire molte auth_request in parallelo. Una connessione
    # SQLite dedicata evita l'uso concorrente della connessione globale. Usa
    # però lo stesso file della connessione attiva, così test e configurazioni
    # con un database alternativo non vengono instradati verso AUTH_DB_PATH.
    database = auth_db.execute("PRAGMA database_list").fetchone()
    database_path = str(database["file"] or AUTH_DB_PATH)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT users.* FROM sessions "
            "JOIN users ON users.id=sessions.user_id WHERE sessions.token=?",
            (token,),
        ).fetchone()


def authenticate_user(email: str, password: str) -> sqlite3.Row:
    user = auth_db.execute(
        "SELECT * FROM users WHERE email=?",
        (email.lower().strip(),),
    ).fetchone()
    if user is None or not bool(user["account_registered"]):
        raise HTTPException(status_code=401, detail="Email o password non corrette")
    digest, _ = hash_password(password, bytes.fromhex(user["password_salt"]))
    if not hmac.compare_digest(digest, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o password non corrette")
    return user


def ensure_grafana_admin() -> None:
    """Keep the local Grafana administrator aligned with Compose credentials."""
    salt = secrets.token_bytes(16)
    digest, salt_hex = hash_password(GRAFANA_ADMIN_PASSWORD, salt)
    now = datetime.now(timezone.utc).isoformat()
    auth_db.execute(
        "INSERT INTO users("
        "id,name,first_name,last_name,email,password_hash,password_salt,role,created_at,"
        "patient_code,fiscal_code,professional_verified"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET email=excluded.email,"
        "password_hash=excluded.password_hash,password_salt=excluded.password_salt,"
        "professional_verified=1",
        (
            "usr_grafana_admin",
            "Amministratore SmartBack",
            "Amministratore",
            "SmartBack",
            "admin@smartback.local",
            digest,
            salt_hex,
            "doctor",
            now,
            None,
            None,
            1,
        ),
    )
    auth_db.commit()


def authenticate_grafana_user(identifier: str, password: str) -> sqlite3.Row:
    normalized = identifier.lower().strip()
    email = (
        "admin@smartback.local"
        if normalized == GRAFANA_ADMIN_USER.lower().strip()
        else normalized
    )
    return authenticate_user(email, password)


def current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    token = authorization.removeprefix("Bearer ").strip()
    row = user_for_session(token)
    if row is None:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    return row


def threshold_profile_for_patient(patient: sqlite3.Row | None) -> ThresholdProfile:
    if patient is None:
        return ThresholdProfile(
            pitch_moderate_deg=MODERATE_DEVIATION_DEG,
            pitch_marked_deg=MARKED_DEVIATION_DEG,
            roll_moderate_deg=MODERATE_ROLL_DEG,
            roll_marked_deg=MARKED_ROLL_DEG,
            persistence_seconds=PERSISTENCE_SECONDS,
        )
    row = auth_db.execute(
        "SELECT moderate_deviation_deg,marked_deviation_deg,moderate_roll_deg,marked_roll_deg,persistence_seconds "
        "FROM monitoring_configs WHERE patient_id=?",
        (patient["id"],),
    ).fetchone()
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
    patient = auth_db.execute(
        "SELECT * FROM users WHERE patient_code=? AND role='patient'", (patient_code,)
    ).fetchone()
    return threshold_profile_for_patient(patient)


def accessible_patient(user: sqlite3.Row, patient_id: str | None = None) -> sqlite3.Row:
    if user["role"] == "patient":
        if patient_id and patient_id != user["id"]:
            raise HTTPException(status_code=403, detail="Non puoi visualizzare i dati di un altro paziente")
        return user
    if not patient_id:
        raise HTTPException(status_code=400, detail="Seleziona un paziente")
    patient = auth_db.execute(
        "SELECT patients.* FROM doctor_patients links "
        "JOIN users patients ON patients.id=links.patient_id "
        "WHERE links.doctor_id=? AND patients.id=?",
        (user["id"], patient_id),
    ).fetchone()
    if patient is None:
        raise HTTPException(status_code=403, detail="Paziente non associato al medico")
    return patient


def accessible_patient_by_code(user: sqlite3.Row, patient_code: str) -> sqlite3.Row:
    if user["role"] == "patient":
        if user["patient_code"] != patient_code:
            raise HTTPException(status_code=403, detail="Non puoi calibrare un altro paziente")
        return user
    if user["id"] == "usr_grafana_admin":
        patient = auth_db.execute(
            "SELECT * FROM users WHERE role='patient' AND patient_code=?",
            (patient_code,),
        ).fetchone()
        if patient is None:
            raise HTTPException(status_code=404, detail="Paziente non trovato")
        return patient
    patient = auth_db.execute(
        "SELECT patients.* FROM doctor_patients links "
        "JOIN users patients ON patients.id=links.patient_id "
        "WHERE links.doctor_id=? AND patients.patient_code=?",
        (user["id"], patient_code),
    ).fetchone()
    if patient is None:
        raise HTTPException(status_code=403, detail="Paziente non associato al medico")
    return patient


def stored_calibration_for_device(
    device_id: str, patient_code: str
) -> tuple[float, float] | None:
    row = auth_db.execute(
        "SELECT calibrations.reference_pitch_deg,calibrations.reference_roll_deg "
        "FROM device_calibrations calibrations "
        "JOIN users patients ON patients.id=calibrations.patient_id "
        "WHERE calibrations.device_id=? AND patients.patient_code=? "
        "AND calibrations.algorithm_version=?",
        (device_id, patient_code, CALIBRATION_ALGORITHM_VERSION),
    ).fetchone()
    if row is None:
        return None
    return float(row["reference_pitch_deg"]), float(row["reference_roll_deg"])


def persist_calibration(
    *,
    patient: sqlite3.Row,
    calibrated_by: sqlite3.Row,
    result: dict[str, float | str],
) -> None:
    auth_db.execute(
        "INSERT INTO device_calibrations("
        "device_id,patient_id,reference_pitch_deg,reference_roll_deg,algorithm_version,"
        "calibrated_at,calibrated_by"
        ") VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(device_id) DO UPDATE SET "
        "patient_id=excluded.patient_id,reference_pitch_deg=excluded.reference_pitch_deg,"
        "reference_roll_deg=excluded.reference_roll_deg,"
        "algorithm_version=excluded.algorithm_version,calibrated_at=excluded.calibrated_at,"
        "calibrated_by=excluded.calibrated_by",
        (
            result["device_id"],
            patient["id"],
            result["reference_pitch_deg"],
            result["reference_roll_deg"],
            CALIBRATION_ALGORITHM_VERSION,
            datetime.now(timezone.utc).isoformat(),
            calibrated_by["id"],
        ),
    )
    auth_db.commit()


def fresh_posture_sample(
    patient_code: str, device_id: str | None = None
) -> dict[str, Any]:
    sample = mqtt_handler.latest_posture if mqtt_handler else None
    if sample is None or sample.get("patient_id") != patient_code:
        raise HTTPException(status_code=409, detail="La maglia del paziente non sta trasmettendo")
    if device_id is not None and sample.get("device_id") != device_id:
        raise HTTPException(status_code=409, detail="Nessun campione corrente per questo dispositivo")
    age_seconds = max(
        0.0,
        datetime.now(timezone.utc).timestamp() - float(sample["timestamp"]) / 1000,
    )
    if age_seconds > DATA_STALE_SECONDS:
        raise HTTPException(status_code=409, detail="Dati troppo vecchi: riconnetti la maglia prima di calibrare")
    return sample


def calibrate_patient_device(
    *,
    user: sqlite3.Row,
    patient_code: str,
    device_id: str | None = None,
    captured_sample: dict[str, Any] | None = None,
) -> dict[str, Any]:
    patient = accessible_patient_by_code(user, patient_code)
    sample = captured_sample or fresh_posture_sample(patient_code, device_id)
    if sample.get("patient_id") != patient_code:
        raise HTTPException(status_code=409, detail="Il campione acquisito appartiene a un altro paziente")
    if device_id is not None and sample.get("device_id") != device_id:
        raise HTTPException(status_code=409, detail="Il campione acquisito appartiene a un altro dispositivo")
    try:
        result = (
            mqtt_handler.calibrate_from_sample(str(sample["device_id"]), sample)
            if captured_sample is not None
            else mqtt_handler.calibrate(str(sample["device_id"]))
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=409,
            detail="Il campione corrente non è più disponibile: riprova la calibrazione",
        ) from exc
    persist_calibration(patient=patient, calibrated_by=user, result=result)
    if influx_manager is not None:
        influx_manager.persist_calibration_reference(
            device_id=str(result["device_id"]),
            patient_code=patient_code,
            reference_pitch_deg=float(result["reference_pitch_deg"]),
            reference_roll_deg=float(result["reference_roll_deg"]),
            selected_pitch_deg=float(sample["pitch_deg"]),
            selected_roll_deg=float(sample["roll_deg"]),
        )
    return {
        **result,
        "patient_id": patient["id"],
        "patient_code": patient_code,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": threshold_profile_for_patient(patient).as_dict(),
    }


def manually_calibrate_patient_device(
    *,
    user: sqlite3.Row,
    patient_code: str,
    pitch_deg: float | None,
    roll_deg: float | None,
) -> dict[str, Any]:
    """Persist references entered by a clinician without requiring live telemetry."""
    patient = accessible_patient_by_code(user, patient_code)
    assignment = auth_db.execute(
        "SELECT assignments.device_id FROM device_assignments assignments "
        "JOIN devices ON devices.device_id=assignments.device_id "
        "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
        "AND devices.archived_at IS NULL LIMIT 1",
        (patient["id"],),
    ).fetchone()
    if assignment is None:
        raise HTTPException(status_code=409, detail="Nessuna maglia attiva assegnata al paziente")
    device_id = str(assignment["device_id"])
    current = auth_db.execute(
        "SELECT reference_pitch_deg,reference_roll_deg FROM device_calibrations "
        "WHERE device_id=? AND patient_id=? AND algorithm_version=?",
        (device_id, patient["id"], CALIBRATION_ALGORITHM_VERSION),
    ).fetchone()
    reference_pitch = (
        float(pitch_deg)
        if pitch_deg is not None
        else float(current["reference_pitch_deg"]) if current else 0.0
    )
    reference_roll = (
        float(roll_deg)
        if roll_deg is not None
        else float(current["reference_roll_deg"]) if current else 0.0
    )
    result: dict[str, float | str] = {
        "device_id": device_id,
        "reference_pitch_deg": round(reference_pitch, 2),
        "reference_roll_deg": round(reference_roll, 2),
    }
    # Apply immediately to the in-memory classifier when the backend is live;
    # the database provider restores the same values after every restart.
    if posture_engine is not None:
        result = posture_engine.calibrate(
            device_id,
            {"pitch_deg": reference_pitch, "roll_deg": reference_roll},
        )
    persist_calibration(patient=patient, calibrated_by=user, result=result)
    if influx_manager is not None:
        influx_manager.persist_calibration_reference(
            device_id=device_id,
            patient_code=patient_code,
            reference_pitch_deg=float(result["reference_pitch_deg"]),
            reference_roll_deg=float(result["reference_roll_deg"]),
            selected_pitch_deg=reference_pitch,
            selected_roll_deg=reference_roll,
        )
    return {
        **result,
        "patient_id": patient["id"],
        "patient_code": patient_code,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": threshold_profile_for_patient(patient).as_dict(),
    }


async def broadcast(payload: dict[str, Any]) -> None:
    stale = []
    payload_patient = str(payload.get("patient_id") or "")
    for socket, patient_code in list(websockets.items()):
        if not payload_patient or payload_patient != patient_code:
            continue
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        websockets.pop(socket, None)


def register_seen_device(device_id: str, quality: str) -> None:
    """Keep a durable inventory of every physical or simulated shirt observed."""
    if auth_db is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        auth_db.execute(
            "INSERT INTO devices(device_id,display_name,source_type,first_seen_at,last_seen_at,quality,has_telemetry) "
            "VALUES (?,?,?,?,?,?,1) ON CONFLICT(device_id) DO UPDATE SET "
            "last_seen_at=excluded.last_seen_at,quality=excluded.quality,has_telemetry=1,"
            "source_type=CASE WHEN excluded.quality='simulated' THEN 'simulated' ELSE devices.source_type END",
            (
                device_id,
                device_id,
                "simulated" if quality == "simulated" else "physical",
                now,
                now,
                quality,
            ),
        )
        auth_db.commit()


def active_device_assignments() -> list[dict[str, str]]:
    if auth_db is None:
        return []
    rows = auth_db.execute(
        "SELECT assignments.device_id,patients.patient_code "
        "FROM device_assignments assignments "
        "JOIN users patients ON patients.id=assignments.patient_id "
        "WHERE assignments.released_at IS NULL"
    ).fetchall()
    return [
        {"device_id": str(row["device_id"]), "patient_id": str(row["patient_code"])}
        for row in rows
    ]


def simulated_device_ids() -> list[str]:
    if auth_db is None:
        return []
    rows = auth_db.execute(
        "SELECT device_id FROM devices "
        "WHERE source_type='simulated' AND archived_at IS NULL ORDER BY device_id"
    ).fetchall()
    return [str(row["device_id"]) for row in rows]


def active_simulated_night_device_ids() -> list[str]:
    """Return simulated shirts whose night session must resume after MQTT reconnect."""
    if auth_db is None:
        return []
    rows = auth_db.execute(
        "SELECT nights.device_id FROM night_monitoring_sessions nights "
        "JOIN devices ON devices.device_id=nights.device_id "
        "WHERE nights.status='active' AND devices.source_type='simulated' "
        "AND devices.archived_at IS NULL"
    ).fetchall()
    return [str(row["device_id"]) for row in rows]


def active_night_session_for_sample(
    device_id: str, patient_code: str
) -> dict[str, str] | None:
    if auth_db is None:
        return None
    row = auth_db.execute(
        "SELECT nights.id,nights.patient_id,nights.device_id "
        "FROM night_monitoring_sessions nights "
        "JOIN users patients ON patients.id=nights.patient_id "
        "WHERE nights.status='active' AND nights.device_id=? AND patients.patient_code=?",
        (device_id, patient_code),
    ).fetchone()
    return dict(row) if row else None


def update_night_summary(
    session_id: str, position: str, elapsed_seconds: float, changed: bool
) -> None:
    if auth_db is None or elapsed_seconds <= 0:
        return
    columns = {
        "supine": "supine_seconds",
        "prone": "prone_seconds",
        "right_side": "right_side_seconds",
        "left_side": "left_side_seconds",
        "unknown": "unknown_seconds",
        "data_gap": "data_gap_seconds",
    }
    column = columns.get(position, "unknown_seconds")
    with database_lock:
        auth_db.execute(
            f"UPDATE night_monitoring_sessions SET {column}={column}+?, "
            "position_changes=position_changes+? WHERE id=? AND status='active'",
            (elapsed_seconds, 1 if changed else 0, session_id),
        )
        auth_db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_handler, influx_manager, posture_engine, night_engine, auth_db
    loop = asyncio.get_running_loop()
    auth_db = init_database(AUTH_DB_PATH)
    ensure_grafana_admin()
    influx_manager = InfluxManager(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
        bucket=INFLUX_BUCKET,
    )
    active_sessions = auth_db.execute(
        "SELECT nights.id,nights.device_id,patients.patient_code "
        "FROM night_monitoring_sessions nights "
        "JOIN users patients ON patients.id=nights.patient_id "
        "WHERE nights.status='active'"
    ).fetchall()
    for active_session in active_sessions:
        try:
            influx_manager.persist_night_session_state(
                patient_code=str(active_session["patient_code"]),
                session_id=str(active_session["id"]),
                device_id=str(active_session["device_id"]),
                active=True,
            )
        except Exception as exc:
            print(f"Unable to reconcile night session {active_session['id']}: {exc}")
    posture_engine = PostureEngine(
        threshold_profile_for_patient_code,
        ema_alpha=POSTURE_EMA_ALPHA,
        hysteresis_deg=POSTURE_HYSTERESIS_DEG,
        calibration_provider=stored_calibration_for_device,
    )
    night_engine = NightPositionEngine(
        session_provider=active_night_session_for_sample,
        summary_updater=update_night_summary,
        persister=influx_manager.persist_night_position,
        gap_seconds=DATA_STALE_SECONDS,
    )
    mqtt_handler = SmartBackMqttHandler(
        host=MQTT_HOST,
        port=MQTT_PORT,
        posture_topic=POSTURE_TOPIC,
        device_topic=DEVICE_TOPIC,
        alert_topic=ALERT_TOPIC,
        stale_seconds=DATA_STALE_SECONDS,
        posture_engine=posture_engine,
        influx=influx_manager,
        broadcast=broadcast,
        device_seen=register_seen_device,
        assignment_provider=active_device_assignments,
        simulated_device_provider=simulated_device_ids,
        active_night_simulation_provider=active_simulated_night_device_ids,
        night_engine=night_engine,
    )
    mqtt_handler.start(loop)
    yield
    await mqtt_handler.stop()
    influx_manager.close()
    auth_db.close()


app = FastAPI(
    title="SmartBack API",
    version="0.1.0",
    description="API del sistema SmartBack per app, portale medico, monitoraggio e smart shirt.",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@system_router.get("/")
def root():
    return {"service": "SmartBack API", "docs": "/docs", "health": "/health"}


@auth_router.post("/api/v1/auth/register", status_code=201)
def register(body: RegisterRequest):
    role = body.role
    email = body.email.lower().strip()
    if auth_db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise HTTPException(status_code=409, detail="Utente già registrato")
    digest, salt = hash_password(body.password)
    full_name = f"{body.first_name} {body.last_name}"
    pending_patient = None
    if role == "patient":
        pending_patient = auth_db.execute(
            "SELECT * FROM users WHERE fiscal_code=? AND role='patient'",
            (body.fiscal_code,),
        ).fetchone()
        if pending_patient is not None and bool(pending_patient["account_registered"]):
            raise HTTPException(
                status_code=409,
                detail="Codice fiscale già associato a un account registrato",
            )
    if pending_patient is not None:
        user_id = str(pending_patient["id"])
        try:
            auth_db.execute(
                "UPDATE users SET name=?,first_name=?,last_name=?,email=?,"
                "password_hash=?,password_salt=?,account_registered=1 WHERE id=?",
                (
                    full_name,
                    body.first_name,
                    body.last_name,
                    email,
                    digest,
                    salt,
                    user_id,
                ),
            )
            auth_db.commit()
        except sqlite3.IntegrityError:
            auth_db.rollback()
            raise HTTPException(status_code=409, detail="Email già registrata") from None
        user = auth_db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return {"access_token": create_session(user_id), "user": public_user(user)}

    user_id = f"usr_{secrets.token_hex(8)}"
    patient_code = f"patient-{user_id.removeprefix('usr_')}" if role == "patient" else None
    try:
        auth_db.execute(
            "INSERT INTO users(id,name,first_name,last_name,email,password_hash,password_salt,role,created_at,patient_code,fiscal_code,professional_verified,account_registered) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (user_id, full_name, body.first_name, body.last_name, email, digest, salt, role,
             datetime.now(timezone.utc).isoformat(), patient_code, body.fiscal_code, 1 if role == "doctor" else 0),
        )
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Email o codice fiscale già registrato") from None
    auth_db.commit()
    user = auth_db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return {"access_token": create_session(user_id), "user": public_user(user)}


@auth_router.post("/api/v1/auth/login")
def login(body: LoginRequest):
    user = authenticate_user(str(body.email), body.password)
    return {"access_token": create_session(user["id"]), "user": public_user(user)}


@grafana_pages_router.get("/grafana-login", response_class=HTMLResponse)
def grafana_login_page():
    return """
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>SmartBack · Portale medico</title><style>
      :root{--bg:#0b0f17;--panel:#151b26;--line:#2a3444;--text:#f4f7fb;--muted:#9da9ba;--blue:#3274d9;--error:#ff8787}
      *{box-sizing:border-box} body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif;padding:24px}
      main{width:min(100%,500px);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:30px;box-shadow:0 18px 55px #0006}
      .brand{display:flex;align-items:center;gap:18px;margin-bottom:20px}.brand-logo{width:132px;height:92px;overflow:hidden;flex:0 0 auto}.brand-logo img{display:block;width:132px;height:112px;object-fit:contain;transform:translateY(-20px)}.brand-copy{min-width:0}
      h1{margin:0 0 8px;font-size:26px}.intro{margin:0 0 22px;color:var(--muted)}
      .tabs{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:5px;background:#0f1520;border-radius:11px;margin-bottom:22px}
      .tab{border:0;border-radius:8px;padding:11px;background:transparent;color:var(--muted);font-weight:800;cursor:pointer}.tab.active{background:#273248;color:white}
      form{display:grid;gap:15px}.hidden{display:none}label{font-weight:650;color:#dce3ec}
      input{display:block;width:100%;height:46px;margin-top:6px;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:#0f1520;color:white;font:inherit;outline:none}
      input:focus{border-color:#5794f2;box-shadow:0 0 0 2px #5794f233}.password-field{position:relative;display:block;margin-top:6px}.password-field input{margin:0;padding-right:48px}
      .password-toggle{position:absolute;right:3px;top:3px;width:40px;height:40px;display:grid;place-items:center;border:0;border-radius:7px;background:transparent;color:#aeb8c7;cursor:pointer}
      .password-toggle:hover,.password-toggle:focus-visible{background:#273248;color:white}.password-toggle svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
      .submit{height:46px;border:0;border-radius:9px;background:var(--blue);color:white;font-weight:800;font-size:15px;cursor:pointer;margin-top:3px}.submit:disabled{opacity:.55;cursor:wait}
      .error{color:var(--error);min-height:22px;margin:0}.hint{font-size:13px;color:var(--muted);margin:-5px 0 0}
      @media(max-width:520px){main{padding:22px}.brand{gap:12px}.brand-logo{width:106px;height:74px}.brand-logo img{width:106px;height:90px;transform:translateY(-16px)}h1{font-size:23px}}
    </style></head><body><main>
      <div class="brand"><span class="brand-logo"><img src="/smartback-assets/logo.png" alt="Logo SmartBack"></span><div class="brand-copy"><h1>SmartBack</h1><p class="intro">Portale medico<br>Accedi oppure crea un account riservato ai medici.</p></div></div>
      <div class="tabs" role="tablist" aria-label="Accesso o registrazione">
        <button id="login-tab" class="tab active" type="button" role="tab" aria-selected="true">Accedi</button>
        <button id="register-tab" class="tab" type="button" role="tab" aria-selected="false">Registrati</button>
      </div>
      <form id="login" autocomplete="on">
        <label>Email<input id="email" type="text" autocomplete="username" required></label>
        <label>Password<span class="password-field"><input id="password" type="password" autocomplete="current-password" required><button class="password-toggle" type="button" data-password="password" aria-label="Mostra password" title="Mostra password"></button></span></label>
        <button class="submit" type="submit">Accedi alla dashboard</button>
        <p id="login-error" class="error" role="alert"></p>
      </form>
      <form id="register" class="hidden" autocomplete="on">
        <label>Nome<input id="first-name" autocomplete="given-name" minlength="2" maxlength="50" required></label>
        <label>Cognome<input id="last-name" autocomplete="family-name" minlength="2" maxlength="50" required></label>
        <label>Email<input id="register-email" type="email" autocomplete="email" required></label>
        <label>Password<span class="password-field"><input id="register-password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required><button class="password-toggle" type="button" data-password="register-password" aria-label="Mostra password" title="Mostra password"></button></span></label>
        <p class="hint">Almeno 8 caratteri, un numero e un simbolo speciale.</p>
        <label>Codice medico<span class="password-field"><input id="medical-code" type="password" autocomplete="off" maxlength="80" required><button class="password-toggle" type="button" data-password="medical-code" data-label="codice medico" aria-label="Mostra codice medico" title="Mostra codice medico"></button></span></label>
        <button class="submit" type="submit">Crea account medico</button>
        <p id="register-error" class="error" role="alert"></p>
      </form>
      <script>
        const eye = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>';
        const eyeOff = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18"/><path d="M10.6 6.1A10.8 10.8 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-2.1 2.8M6.2 6.2C3.8 8 2.5 12 2.5 12s3.5 6 9.5 6c1.7 0 3.2-.5 4.5-1.2"/></svg>';
        document.querySelectorAll('.password-toggle').forEach(button => {
          const input = document.getElementById(button.dataset.password);
          const fieldLabel = button.dataset.label || 'password';
          button.innerHTML = eye;
          button.addEventListener('click', () => {
            const reveal = input.type === 'password';
            input.type = reveal ? 'text' : 'password';
            button.innerHTML = reveal ? eyeOff : eye;
            button.setAttribute('aria-label', `${reveal ? 'Nascondi' : 'Mostra'} ${fieldLabel}`);
            button.setAttribute('title', `${reveal ? 'Nascondi' : 'Mostra'} ${fieldLabel}`);
          });
        });
        const loginForm = document.getElementById('login');
        const registerForm = document.getElementById('register');
        function show(mode) {
          const login = mode === 'login';
          loginForm.classList.toggle('hidden', !login); registerForm.classList.toggle('hidden', login);
          document.getElementById('login-tab').classList.toggle('active', login);
          document.getElementById('register-tab').classList.toggle('active', !login);
          document.getElementById('login-tab').setAttribute('aria-selected', String(login));
          document.getElementById('register-tab').setAttribute('aria-selected', String(!login));
        }
        document.getElementById('login-tab').addEventListener('click', () => show('login'));
        document.getElementById('register-tab').addEventListener('click', () => show('register'));
        const detail = (body, fallback) => Array.isArray(body.detail) ? body.detail.map(item => item.msg).join(' · ') : (body.detail || fallback);
        loginForm.addEventListener('submit', async event => {
          event.preventDefault(); const error = document.getElementById('login-error'); error.textContent = '';
          const response = await fetch('/api/v1/grafana/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});
          const body = await response.json().catch(() => ({}));
          if(response.ok){window.location.assign(body.redirect || '/smartback/');return} error.textContent=detail(body,'Accesso non riuscito');
        });
        registerForm.addEventListener('submit', async event => {
          event.preventDefault(); const error = document.getElementById('register-error'); error.textContent = '';
          const response = await fetch('/api/v1/grafana/register', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({first_name:document.getElementById('first-name').value,last_name:document.getElementById('last-name').value,email:document.getElementById('register-email').value,password:document.getElementById('register-password').value,role:'doctor',medical_code:document.getElementById('medical-code').value})});
          const body = await response.json().catch(() => ({}));
          if(response.ok){window.location.assign(body.redirect || '/smartback/');return} error.textContent=detail(body,'Registrazione non riuscita');
        });
      </script>
    </main></body></html>
    """


@grafana_pages_router.get(
    "/smartback-assets/logo.png",
    response_class=FileResponse,
    include_in_schema=False,
)
def smartback_logo():
    candidates = (
        Path("/app/assets/smartback-logo-transparent.png"),
        Path(__file__).resolve().parents[2]
        / "mobile"
        / "app"
        / "assets"
        / "smartback-logo-transparent.png",
    )
    for candidate in candidates:
        if candidate.is_file():
            return FileResponse(candidate, media_type="image/png")
    raise HTTPException(status_code=404, detail="Logo SmartBack non disponibile")


@grafana_router.post("/api/v1/grafana/login")
def grafana_login(body: GrafanaLoginRequest, response: Response):
    user = authenticate_grafana_user(body.email, body.password)
    if user["role"] != "doctor" or not bool(user["professional_verified"]):
        raise HTTPException(status_code=403, detail="Accesso riservato ai medici verificati")
    token = create_session(user["id"])
    response.set_cookie(
        GRAFANA_SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {"status": "ok", "redirect": "/smartback/"}


@grafana_router.post("/api/v1/grafana/register", status_code=201)
def grafana_register_doctor(body: RegisterRequest, response: Response):
    if body.role != "doctor":
        raise HTTPException(
            status_code=403,
            detail="Da questa pagina è consentita soltanto la registrazione medica",
        )
    registered = register(body)
    token = str(registered["access_token"])
    response.set_cookie(
        GRAFANA_SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return {"status": "ok", "redirect": "/smartback/"}


def verified_grafana_user(smartback_grafana_session: str | None) -> sqlite3.Row:
    if not smartback_grafana_session:
        raise HTTPException(status_code=401, detail="Sessione Grafana richiesta")
    user = user_for_session(smartback_grafana_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Sessione Grafana non valida")
    if user["role"] != "doctor" or not bool(user["professional_verified"]):
        raise HTTPException(status_code=403, detail="Accesso riservato ai medici verificati")
    return user


def medical_portal_data(user: sqlite3.Row) -> dict[str, Any]:
    patients = auth_db.execute(
        "SELECT patients.*, links.created_at AS associated_at, "
        "assignments.device_id AS assigned_device "
        "FROM doctor_patients links "
        "JOIN users patients ON patients.id=links.patient_id "
        "LEFT JOIN device_assignments assignments "
        "ON assignments.patient_id=patients.id AND assignments.released_at IS NULL "
        "WHERE links.doctor_id=? ORDER BY patients.name COLLATE NOCASE",
        (user["id"],),
    ).fetchall()
    devices = auth_db.execute(
        "SELECT devices.*, assignments.id AS assignment_id, assignments.patient_id, "
        "assignments.assigned_at, patients.patient_code, "
        "CASE WHEN links.doctor_id IS NOT NULL THEN patients.name ELSE NULL END AS patient_name "
        "FROM devices LEFT JOIN device_assignments assignments "
        "ON assignments.device_id=devices.device_id AND assignments.released_at IS NULL "
        "LEFT JOIN users patients ON patients.id=assignments.patient_id "
        "LEFT JOIN doctor_patients links ON links.patient_id=patients.id AND links.doctor_id=? "
        "WHERE devices.archived_at IS NULL AND devices.owner_doctor_id=? "
        "ORDER BY devices.doctor_device_number",
        (user["id"], user["id"]),
    ).fetchall()
    discovered_devices = auth_db.execute(
        "SELECT device_id,last_seen_at,quality FROM devices "
        "WHERE owner_doctor_id IS NULL AND archived_at IS NULL AND has_telemetry=1 "
        "ORDER BY last_seen_at DESC,device_id COLLATE NOCASE"
    ).fetchall()
    patient_items = [
        {
            **public_user(row),
            "associated_at": row["associated_at"],
            "assigned_device": row["assigned_device"],
        }
        for row in patients
    ]
    device_items = [
        {
            "device_id": row["device_id"],
            "inventory_id": row["doctor_device_number"],
            "display_name": row["display_name"] or row["device_id"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "quality": row["quality"],
            "source_type": row["source_type"],
            "has_telemetry": bool(row["has_telemetry"]),
            "available": row["assignment_id"] is None,
            "assigned_at": row["assigned_at"],
            "patient_code": row["patient_code"],
            "patient_name": row["patient_name"] or (
                "Altro paziente" if row["assignment_id"] is not None else None
            ),
        }
        for row in devices
    ]
    return {
        "doctor": public_user(user),
        "patients": patient_items,
        "devices": device_items,
        "discovered_devices": [
            {
                "device_id": row["device_id"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in discovered_devices
        ],
        "summary": {
            "patients": len(patient_items),
            "devices_total": len(device_items),
            "devices_available": sum(1 for item in device_items if item["available"]),
            "devices_assigned": sum(1 for item in device_items if not item["available"]),
        },
    }


@grafana_router.get("/api/v1/grafana/home")
def grafana_home_data(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    return medical_portal_data(verified_grafana_user(smartback_grafana_session))


@grafana_router.post("/api/v1/grafana/patients", status_code=201)
def grafana_associate_patient(
    body: AssociatePatientRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = auth_db.execute(
        "SELECT * FROM users WHERE fiscal_code=? AND role='patient'",
        (body.fiscal_code,),
    ).fetchone()
    if patient is None:
        patient_id = f"usr_{secrets.token_hex(8)}"
        patient_code = f"patient-{patient_id.removeprefix('usr_')}"
        placeholder_email = f"pending-{secrets.token_hex(12)}@smartback.local"
        placeholder_digest, placeholder_salt = hash_password(secrets.token_urlsafe(32))
        auth_db.execute(
            "INSERT INTO users("
            "id,name,first_name,last_name,email,password_hash,password_salt,role,created_at,"
            "patient_code,fiscal_code,professional_verified,account_registered"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
            (
                patient_id,
                "Paziente non registrato",
                "Paziente",
                "non registrato",
                placeholder_email,
                placeholder_digest,
                placeholder_salt,
                "patient",
                datetime.now(timezone.utc).isoformat(),
                patient_code,
                body.fiscal_code,
                0,
            ),
        )
        auth_db.commit()
        patient = auth_db.execute("SELECT * FROM users WHERE id=?", (patient_id,)).fetchone()
    try:
        auth_db.execute(
            "INSERT INTO doctor_patients(doctor_id,patient_id,created_at) VALUES (?,?,?)",
            (user["id"], patient["id"], datetime.now(timezone.utc).isoformat()),
        )
        auth_db.commit()
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Paziente già presente nella lista") from None
    return public_user(patient)


@grafana_router.delete("/api/v1/grafana/patients/{patient_code}", status_code=204)
def grafana_remove_patient(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    assignments = auth_db.execute(
        "SELECT assignments.id,assignments.device_id FROM device_assignments assignments "
        "JOIN devices ON devices.device_id=assignments.device_id "
        "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
        "AND devices.owner_doctor_id=?",
        (patient["id"], user["id"]),
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        auth_db.execute(
            "UPDATE device_assignments SET released_at=?,released_by=? "
            "WHERE patient_id=? AND released_at IS NULL AND device_id IN "
            "(SELECT device_id FROM devices WHERE owner_doctor_id=?)",
            (now, user["id"], patient["id"], user["id"]),
        )
        auth_db.execute(
            "DELETE FROM doctor_patients WHERE doctor_id=? AND patient_id=?",
            (user["id"], patient["id"]),
        )
        auth_db.commit()
    if mqtt_handler:
        for assignment in assignments:
            mqtt_handler.publish_device_assignment(str(assignment["device_id"]), None)
    return Response(status_code=204)


@grafana_router.post("/api/v1/grafana/devices", status_code=201)
def grafana_create_device(
    body: DeviceCreateRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with database_lock:
            next_number = auth_db.execute(
                "SELECT COALESCE(MAX(doctor_device_number),-1)+1 AS next_number "
                "FROM devices WHERE owner_doctor_id=?",
                (user["id"],),
            ).fetchone()["next_number"]
            device_id = f"sim-{str(user['id']).removeprefix('usr_')}-{int(next_number)}"
            auth_db.execute(
                "INSERT INTO devices(device_id,display_name,owner_doctor_id,doctor_device_number,"
                "source_type,first_seen_at,last_seen_at,quality,has_telemetry) "
                "VALUES (?,?,?,?,?,?,?,?,0)",
                (
                    device_id,
                    body.display_name,
                    user["id"],
                    int(next_number),
                    "simulated",
                    now,
                    now,
                    "simulated",
                ),
            )
            auth_db.commit()
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Impossibile generare la maglia di test") from None
    if mqtt_handler:
        mqtt_handler.publish_simulated_device(device_id, active=True)
    return {
        "device_id": device_id,
        "inventory_id": int(next_number),
        "display_name": body.display_name,
        "has_telemetry": False,
    }


@grafana_router.post(
    "/api/v1/grafana/devices/discovered/{device_id}/claim",
    status_code=201,
)
def grafana_claim_discovered_device(
    device_id: str,
    body: DeviceClaimRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    with database_lock:
        next_number = auth_db.execute(
            "SELECT COALESCE(MAX(doctor_device_number),-1)+1 AS next_number "
            "FROM devices WHERE owner_doctor_id=?",
            (user["id"],),
        ).fetchone()["next_number"]
        cursor = auth_db.execute(
            "UPDATE devices SET owner_doctor_id=?,doctor_device_number=?,display_name=? "
            "WHERE device_id=? AND owner_doctor_id IS NULL AND archived_at IS NULL "
            "AND has_telemetry=1",
            (user["id"], int(next_number), body.display_name, device_id),
        )
        if cursor.rowcount != 1:
            auth_db.rollback()
            raise HTTPException(
                status_code=409,
                detail="La maglia non è più disponibile o è già stata acquisita",
            )
        auth_db.commit()
    return {
        "device_id": device_id,
        "inventory_id": int(next_number),
        "display_name": body.display_name,
        "has_telemetry": True,
    }


@grafana_router.delete("/api/v1/grafana/devices/{device_id}", status_code=204)
def grafana_remove_device(
    device_id: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    device = auth_db.execute(
        "SELECT devices.source_type,assignments.patient_id "
        "FROM devices LEFT JOIN device_assignments assignments "
        "ON assignments.device_id=devices.device_id AND assignments.released_at IS NULL "
        "WHERE devices.device_id=? AND devices.owner_doctor_id=? "
        "AND devices.archived_at IS NULL",
        (device_id, user["id"]),
    ).fetchone()
    if device is None:
        raise HTTPException(status_code=404, detail="Maglia non trovata")
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        auth_db.execute(
            "UPDATE device_assignments SET released_at=?,released_by=? "
            "WHERE device_id=? AND released_at IS NULL",
            (now, user["id"], device_id),
        )
        if device["source_type"] == "simulated":
            auth_db.execute(
                "UPDATE devices SET archived_at=? WHERE device_id=?",
                (now, device_id),
            )
        else:
            # A physical shirt can be transferred between medical inventories.
            # Removing it relinquishes ownership; its telemetry and assignment
            # history remain intact and it becomes discoverable again.
            auth_db.execute(
                "UPDATE devices SET owner_doctor_id=NULL,doctor_device_number=NULL,"
                "archived_at=NULL WHERE device_id=?",
                (device_id,),
            )
        auth_db.commit()
    if mqtt_handler:
        mqtt_handler.publish_device_assignment(device_id, None)
        if device["source_type"] == "simulated":
            mqtt_handler.publish_simulated_device(device_id, active=False)
    return Response(status_code=204)


@grafana_router.put("/api/v1/grafana/devices/{device_id}/assignment")
def grafana_assign_device(
    device_id: str,
    body: DeviceAssignmentRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, body.patient_code)
    if auth_db.execute(
        "SELECT 1 FROM devices WHERE device_id=? AND owner_doctor_id=? "
        "AND archived_at IS NULL",
        (device_id, user["id"]),
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="Maglia non presente nell'inventario")
    now = datetime.now(timezone.utc).isoformat()
    try:
        auth_db.execute(
            "INSERT INTO device_assignments(device_id,patient_id,assigned_at,assigned_by) "
            "VALUES (?,?,?,?)",
            (device_id, patient["id"], now, user["id"]),
        )
        auth_db.commit()
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(
            status_code=409,
            detail="La maglia o il paziente possiedono già un'assegnazione attiva",
        ) from None
    if mqtt_handler:
        mqtt_handler.publish_device_assignment(device_id, str(patient["patient_code"]))
    return {"device_id": device_id, "patient_code": patient["patient_code"], "assigned_at": now}


@grafana_router.delete("/api/v1/grafana/devices/{device_id}/assignment", status_code=204)
def grafana_release_device(
    device_id: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    assignment = auth_db.execute(
        "SELECT assignments.id FROM device_assignments assignments "
        "JOIN devices ON devices.device_id=assignments.device_id "
        "WHERE assignments.device_id=? AND assignments.released_at IS NULL "
        "AND devices.owner_doctor_id=?",
        (device_id, user["id"]),
    ).fetchone()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assegnazione attiva non trovata")
    auth_db.execute(
        "UPDATE device_assignments SET released_at=?,released_by=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), user["id"], assignment["id"]),
    )
    auth_db.commit()
    if mqtt_handler:
        mqtt_handler.publish_device_assignment(device_id, None)
    return Response(status_code=204)


@grafana_pages_router.get("/smartback/", response_class=HTMLResponse)
def medical_portal_page(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    try:
        user = verified_grafana_user(smartback_grafana_session)
    except HTTPException:
        return RedirectResponse(url="/grafana-login", status_code=303)
    doctor_name = html.escape(str(user["name"]))
    return f"""
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>SmartBack · Pazienti</title><style>
    :root{{--bg:#0b0f17;--panel:#151b26;--line:#2a3444;--text:#f4f7fb;--muted:#9da9ba;--blue:#3274d9;--green:#2fb344;--red:#e5484d}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif}}
    header{{display:flex;justify-content:space-between;align-items:center;padding:16px 5vw;border-bottom:1px solid var(--line)}}
    .brand{{display:flex;align-items:center;gap:16px}} .brand-logo{{width:118px;height:82px;overflow:hidden;flex:0 0 auto}} .brand-logo img{{display:block;width:118px;height:100px;object-fit:contain;transform:translateY(-18px)}}
    main{{max-width:1200px;margin:auto;padding:34px 5vw 60px}} h1{{margin:0;font-size:25px}} h2{{font-size:20px;margin:0 0 7px}}
    .muted{{color:var(--muted)}} .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
    main>section:not(.stats){{margin-top:42px}} main>section>.toolbar{{margin-bottom:20px}}
    .stat,.card,.device{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}}
    .stat b{{display:block;font-size:28px;margin-top:5px}} .toolbar{{display:flex;justify-content:space-between;align-items:center;gap:15px}}
    button,.button{{border:0;border-radius:9px;padding:11px 16px;background:var(--blue);color:white;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}}
    .day-button{{background:#e6b94a;color:#18120a}} .night-button{{background:#315a9d}} .secondary{{background:#273248}} .danger{{background:#54252b}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:14px}}
    .device-grid{{grid-template-columns:repeat(3,minmax(0,1fr));justify-content:start}}
    .empty-state{{grid-column:1/-1;width:100%}}
    .card h3,.device h3{{margin:0 0 4px;font-size:18px}} .actions{{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}}
    .patient-controls{{display:grid;gap:12px;margin-top:18px}} .patient-controls .actions{{margin-top:0;align-items:stretch;flex-wrap:nowrap}}
    .patient-controls .actions button{{flex:1 1 0;min-width:0}} button:disabled{{cursor:not-allowed;opacity:.48}}
    .badge{{display:inline-block;padding:4px 9px;border-radius:99px;background:#263247;color:#cbd5e1;font-size:12px;font-weight:700}}
    .available{{background:#173b29;color:#8ce99a}} .assigned{{background:#412b16;color:#ffc078}}
    select,input{{width:100%;background:#0f1520;color:white;border:1px solid var(--line);border-radius:8px;padding:10px}}
    .shirt-select{{min-height:50px;padding:0 15px;font-size:16px;font-weight:650}}
    .shirt-select:disabled{{color:#9da9ba;background:#111722;opacity:1}}
    dialog{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:14px;max-width:460px;width:calc(100% - 30px);padding:24px}} dialog::backdrop{{background:#000a}}
    #deviceDialog{{max-width:520px;padding:30px}} #deviceDialog h3{{margin:20px 0 8px;font-size:20px}}
    #deviceDialog h2+h3{{margin-top:24px}} #deviceDialog h3+.muted{{margin:0 0 16px;line-height:1.45}}
    #deviceDialog form{{gap:10px!important}} #deviceDialog form label{{display:grid;gap:8px;font-size:16px;font-weight:700}}
    #deviceDialog form .actions{{margin-top:4px}} #deviceDialog form p:empty{{display:none}}
    #deviceDialog #deviceForm .actions .secondary{{margin-left:auto}}
    #deviceDialog hr{{margin:20px 0!important}}
    #patientDialog .actions .secondary{{margin-left:auto}}
    #deviceDialog select,#deviceDialog input{{height:54px;padding:0 16px;font-size:16px}}
    @media(max-width:900px){{.device-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @media(max-width:720px){{.stats{{grid-template-columns:repeat(2,1fr)}}.device-grid{{grid-template-columns:1fr}}header{{align-items:flex-start;gap:15px}}.brand-logo{{width:92px;height:64px}}.brand-logo img{{width:92px;height:78px;transform:translateY(-14px)}}}}
    </style></head><body><header><div class="brand"><span class="brand-logo"><img src="/smartback-assets/logo.png" alt="Logo SmartBack"></span><div><h1>SmartBack</h1><div class="muted">Portale medico</div></div></div>
    <div><span class="muted">{doctor_name}</span> · <a href="/grafana-logout" style="color:#8ab4ff">Esci</a></div></header>
    <main><section class="stats" id="stats"></section>
    <section><div class="toolbar"><div><h2>I miei pazienti</h2><div class="muted">Seleziona la scheda clinica da consultare.</div></div>
    <button onclick="patientDialog.showModal()">＋ Aggiungi paziente</button></div><div class="grid" id="patients"></div></section>
    <section><div class="toolbar"><div><h2>Lista magliette</h2><div class="muted">Inventario e assegnazioni attive.</div></div>
    <button onclick="deviceDialog.showModal()">＋ Aggiungi maglia</button></div><div class="grid device-grid" id="devices"></div></section></main>
    <dialog id="patientDialog"><h2 style="margin-top:0">Aggiungi un paziente</h2><p class="muted">Inserisci il codice fiscale. Il paziente potrà creare il proprio account SmartBack anche in seguito.</p>
    <form id="patientForm"><label>Codice fiscale<input id="fiscalCode" maxlength="16" required style="margin-top:6px;text-transform:uppercase"></label>
    <p id="patientError" style="color:#ff8787;min-height:22px"></p><div class="actions"><button type="submit">Associa</button><button type="button" class="secondary" onclick="patientDialog.close()">Annulla</button></div></form></dialog>
    <dialog id="deviceDialog"><h2 style="margin-top:0">Aggiungi una maglia</h2>
    <h3>Maglie rilevate disponibili</h3><p class="muted">Il codice tecnico viene acquisito automaticamente dai dati ricevuti.</p>
    <form id="claimDeviceForm" style="display:grid;gap:14px"><label>Maglia rilevata<select id="detectedDevice" required></select></label>
    <label>Nome maglia<input id="detectedDeviceName" placeholder="Maglia ambulatorio" required></label>
    <p id="claimDeviceError" style="color:#ff8787;min-height:22px;margin:0"></p><div class="actions"><button id="claimDeviceButton" type="submit">Acquisisci maglia</button></div></form>
    <hr style="border:0;border-top:1px solid var(--line);margin:24px 0">
    <h3>Crea una maglia di test</h3><p class="muted">Il codice tecnico simulato viene generato automaticamente.</p>
    <form id="deviceForm" style="display:grid;gap:14px"><label>Nome maglia<input id="deviceName" placeholder="Maglia test" required></label>
    <p id="deviceError" style="color:#ff8787;min-height:22px;margin:0"></p><div class="actions"><button type="submit">Crea maglia di test</button><button type="button" class="secondary" onclick="deviceDialog.close()">Annulla</button></div></form></dialog>
    <script>
    const esc=s=>String(s??"").replace(/[&<>\"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}}[c]));
    let state={{patients:[],devices:[],discovered_devices:[],summary:{{}}}};
    async function request(url,options={{}}){{const r=await fetch(url,{{...options,headers:{{"Content-Type":"application/json",...(options.headers||{{}})}}}});if(r.status===401)location.href="/grafana-login";if(!r.ok){{const b=await r.json().catch(()=>({{}}));throw Error(b.detail||"Operazione non riuscita")}}return r.status===204?null:r.json()}}
    async function load(){{state=await request("/api/v1/grafana/home");render()}}
    function render(){{const s=state.summary;stats.innerHTML=[["Pazienti",s.patients],["Maglie totali",s.devices_total],["Maglie disponibili",s.devices_available],["Maglie assegnate",s.devices_assigned]].map(x=>`<div class="stat"><span class="muted">${{x[0]}}</span><b>${{x[1]}}</b></div>`).join("");
    patients.innerHTML=state.patients.length?state.patients.map(p=>{{
      const code=encodeURIComponent(p.patient_code);
      const free=state.devices.filter(d=>d.available);
      const assigned=Boolean(p.assigned_device);
      const canAssign=!assigned&&free.length>0;
      const shirtOptions=assigned
        ? '<option>Maglia già associata</option>'
        : free.length
          ? free.map(d=>`<option value="${{esc(d.device_id)}}">${{esc(d.display_name)}}</option>`).join('')
          : '<option>Nessuna maglia disponibile</option>';
      const shirtAction=assigned
        ? `<button class="danger" onclick="releaseShirt('${{esc(p.assigned_device)}}')">Libera maglia</button>`
        : `<button ${{canAssign?'':'disabled'}} onclick="assign('${{esc(p.id)}}','${{esc(p.patient_code)}}')">Assegna maglia</button>`;
      return `<article class="card"><h3>${{esc(p.name)}}</h3><div class="muted">${{esc(p.patient_code)}}</div><p><span class="badge ${{p.account_registered?'available':''}}">${{p.account_registered?'Account registrato':'Account non registrato'}}</span> ${{assigned?`<span class="badge assigned">Maglia ${{esc(p.assigned_device)}}</span>`:'<span class="badge">Nessuna maglia</span>'}}</p><div class="actions"><a class="button day-button" href="/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id=${{code}}&refresh=1s">DIURNO</a><a class="button day-button" href="/grafana/d/smartback-history/smartback-storico-paziente?var-patient_id=${{code}}">STORICO D</a><a class="button night-button" href="/grafana/d/smartback-night/smartback-monitoraggio-notturno?var-patient_id=${{code}}&refresh=1s">NOTTURNO</a><a class="button night-button" href="/grafana/d/smartback-night-history/smartback-storico-notturno?var-patient_id=${{code}}">STORICO N</a></div><div class="patient-controls"><select class="shirt-select" id="shirt-${{esc(p.id)}}" aria-label="Maglia da associare a ${{esc(p.name)}}" ${{canAssign?'':'disabled'}}>${{shirtOptions}}</select><div class="actions">${{shirtAction}}<button class="danger" onclick="removePatient('${{esc(p.patient_code)}}','${{esc(p.name)}}')">Rimuovi paziente</button></div></div></article>`
    }}).join(""):'<div class="card muted empty-state">Nessun paziente associato.</div>';
    devices.innerHTML=state.devices.length?state.devices.map(d=>`<article class="device"><h3>${{esc(d.display_name)}}</h3><div class="muted">ID ${{esc(d.inventory_id)}} · ${{esc(d.device_id)}}</div><p><span class="badge ${{d.has_telemetry?'available':''}}">${{d.has_telemetry?'Connessa':'Non connessa'}}</span> <span class="badge ${{d.available?'available':'assigned'}}">${{d.available?'Disponibile':'Assegnata'}}</span></p>${{d.patient_name?`<div>Assegnata a: <b>${{esc(d.patient_name)}}</b></div>`:''}}<div class="actions">${{!d.available&&d.patient_name!=='Altro paziente'?`<button class="danger" onclick="releaseShirt('${{esc(d.device_id)}}')">Libera maglia</button>`:''}}<button class="danger" onclick="removeDevice('${{esc(d.device_id)}}','${{esc(d.display_name)}}')">Rimuovi maglia</button></div></article>`).join(""):'<div class="device muted empty-state">Nessuna maglia registrata.</div>';
    const detected=state.discovered_devices||[];detectedDevice.innerHTML=detected.length?detected.map(d=>`<option value="${{esc(d.device_id)}}">${{esc(d.device_id)}}</option>`).join(''):'<option value="">Nessuna maglia rilevata</option>';claimDeviceButton.disabled=!detected.length;detectedDevice.disabled=!detected.length;detectedDeviceName.disabled=!detected.length}}
    async function assign(patientId,patientCode){{const device=document.getElementById('shirt-'+patientId).value;await request('/api/v1/grafana/devices/'+encodeURIComponent(device)+'/assignment',{{method:'PUT',body:JSON.stringify({{patient_code:patientCode}})}});await load()}}
    async function releaseShirt(device){{if(!confirm('Liberare questa maglia? Lo storico precedente resterà associato al paziente.'))return;await request('/api/v1/grafana/devices/'+encodeURIComponent(device)+'/assignment',{{method:'DELETE'}});await load()}}
    async function removePatient(code,name){{if(!confirm(`Rimuovere ${{name}} dalla lista dei pazienti? La maglia verrà liberata, ma account e storico resteranno conservati.`))return;await request('/api/v1/grafana/patients/'+encodeURIComponent(code),{{method:'DELETE'}});await load()}}
    async function removeDevice(device,name){{if(!confirm(`Rimuovere ${{name}} dall'inventario? Le assegnazioni e lo storico resteranno conservati.`))return;await request('/api/v1/grafana/devices/'+encodeURIComponent(device),{{method:'DELETE'}});await load()}}
    patientForm.addEventListener('submit',async e=>{{e.preventDefault();patientError.textContent='';try{{await request('/api/v1/grafana/patients',{{method:'POST',body:JSON.stringify({{fiscal_code:fiscalCode.value}})}});patientDialog.close();patientForm.reset();await load()}}catch(err){{patientError.textContent=err.message}}}});load().catch(e=>document.querySelector('main').innerHTML='<p>'+esc(e.message)+'</p>');
    claimDeviceForm.addEventListener('submit',async e=>{{e.preventDefault();claimDeviceError.textContent='';const code=detectedDevice.value;if(!code)return;if(!confirm(`Acquisire la maglia rilevata ${{code}} nel proprio inventario?`))return;try{{await request('/api/v1/grafana/devices/discovered/'+encodeURIComponent(code)+'/claim',{{method:'POST',body:JSON.stringify({{display_name:detectedDeviceName.value}})}});deviceDialog.close();claimDeviceForm.reset();await load()}}catch(err){{claimDeviceError.textContent=err.message}}}});
    deviceForm.addEventListener('submit',async e=>{{e.preventDefault();deviceError.textContent='';try{{await request('/api/v1/grafana/devices',{{method:'POST',body:JSON.stringify({{display_name:deviceName.value}})}});deviceDialog.close();deviceForm.reset();await load()}}catch(err){{deviceError.textContent=err.message}}}});
    </script></body></html>
    """


@grafana_router.get("/api/v1/grafana/auth")
def grafana_auth(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    return Response(
        status_code=200,
        headers={
            "X-WEBAUTH-USER": user["email"],
            "X-WEBAUTH-NAME": user["name"],
            "X-WEBAUTH-ROLE": "Viewer",
        },
    )


@grafana_router.post("/api/v1/grafana/token-rotation")
def grafana_token_rotation(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    # Con auth proxy non esiste un token Grafana da ruotare. Il frontend
    # richiede comunque questo endpoint e, su 401, ricarica l'intera pagina.
    verified_grafana_user(smartback_grafana_session)
    return {"status": "ok"}


@grafana_router.post("/api/v1/grafana/patients/{patient_code}/calibration")
def grafana_calibrate_patient(
    patient_code: str,
    body: CalibrationConfirmation,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    if not body.confirmed:
        raise HTTPException(
            status_code=409,
            detail="Conferma esplicita richiesta prima di modificare la calibrazione",
        )
    return calibrate_patient_device(user=user, patient_code=patient_code)


@grafana_router.post(
    "/api/v1/grafana/patients/{patient_code}/calibration-snapshot",
    status_code=204,
)
def grafana_capture_calibration_sample(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    """Freeze the reference sample at the instant CALIBRA is pressed."""
    user = verified_grafana_user(smartback_grafana_session)
    accessible_patient_by_code(user, patient_code)
    sample = fresh_posture_sample(patient_code)
    pending_grafana_calibrations[(str(user["id"]), patient_code)] = {
        "sample": dict(sample),
        "captured_at": datetime.now(timezone.utc),
    }
    return Response(status_code=204)


@grafana_router.post(
    "/api/v1/grafana/patients/{patient_code}/calibration-form",
    status_code=204,
)
def grafana_calibrate_patient_form(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    """Calibration target for the dashboard modal's background form."""
    user = verified_grafana_user(smartback_grafana_session)
    pending = pending_grafana_calibrations.pop((str(user["id"]), patient_code), None)
    if pending is None:
        raise HTTPException(
            status_code=409,
            detail="Campione di calibrazione assente: premi nuovamente CALIBRA",
        )
    if datetime.now(timezone.utc) - pending["captured_at"] > timedelta(minutes=2):
        raise HTTPException(
            status_code=409,
            detail="Campione di calibrazione scaduto: premi nuovamente CALIBRA",
        )
    calibrate_patient_device(
        user=user,
        patient_code=patient_code,
        captured_sample=pending["sample"],
    )
    return Response(status_code=204)


@grafana_router.post("/api/v1/grafana/patients/{patient_code}/manual-calibration")
def grafana_manual_calibration(
    patient_code: str,
    body: ManualCalibrationRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    return manually_calibrate_patient_device(
        user=user,
        patient_code=patient_code,
        pitch_deg=body.pitch_deg,
        roll_deg=body.roll_deg,
    )


@grafana_pages_router.get(
    "/api/v1/grafana/patients/{patient_code}/calibration-control",
    response_class=HTMLResponse,
)
def grafana_calibration_control(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    assignment = auth_db.execute(
        "SELECT device_id FROM device_assignments "
        "WHERE patient_id=? AND released_at IS NULL LIMIT 1",
        (patient["id"],),
    ).fetchone()
    current = None
    if assignment is not None:
        current = auth_db.execute(
            "SELECT reference_pitch_deg,reference_roll_deg FROM device_calibrations "
            "WHERE device_id=? AND patient_id=? AND algorithm_version=?",
            (assignment["device_id"], patient["id"], CALIBRATION_ALGORITHM_VERSION),
        ).fetchone()
    pitch = float(current["reference_pitch_deg"]) if current else 0.0
    roll = float(current["reference_roll_deg"]) if current else 0.0
    safe_patient = html.escape(patient_code, quote=True)
    return HTMLResponse(f"""
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <style>
      *{{box-sizing:border-box}} body{{margin:0;background:#111217;color:#f2f4f7;font:15px system-ui,sans-serif}}
      main{{min-height:148px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;align-items:stretch;padding:10px}}
      .cell{{min-width:0;border:1px solid #34373d;border-radius:10px;background:#181b1f;padding:14px;display:flex;flex-direction:column;justify-content:center}}
      label{{display:block;margin-bottom:8px;color:#c7c9d1;font-weight:700}}
      .input{{display:flex;align-items:center;gap:9px}} input{{width:100%;min-width:0;padding:11px 12px;border:1px solid #475467;border-radius:7px;background:#111217;color:#fff;font-size:19px;font-weight:650;outline:none}}
      input:focus{{border-color:#5794f2;box-shadow:0 0 0 2px rgba(87,148,242,.2)}}
      button{{border:0;border-radius:8px;background:#3274d9;color:#fff;cursor:pointer;font-weight:750}}
      #auto{{width:100%;padding:14px;font-size:20px}} .apply{{width:100%;margin-top:10px;padding:9px 13px;font-size:13px}}
      @media(max-width:650px){{main{{grid-template-columns:1fr}}}}
    </style></head><body><main>
      <div class="cell"><label>Cal. Live</label><button id="auto" type="button">CALIBRA</button></div>
      <div class="cell"><label for="pitch">Cal. Manuale P</label><div class="input"><input id="pitch" type="text" value="{pitch:.1f}" inputmode="decimal" autocomplete="off" data-min="-180" data-max="180"><span>°</span></div><button id="apply-pitch" class="apply" type="button">APPLICA</button></div>
      <div class="cell"><label for="roll">Cal. Manuale R</label><div class="input"><input id="roll" type="text" value="{roll:.1f}" inputmode="decimal" autocomplete="off" data-min="-90" data-max="90"><span>°</span></div><button id="apply-roll" class="apply" type="button">APPLICA</button></div>
    </main><script>
      const endpoint = '/api/v1/grafana/patients/' + encodeURIComponent('{safe_patient}');
      async function errorMessage(response) {{
        const body = await response.json().catch(() => ({{}}));
        return body.detail || 'Operazione non riuscita';
      }}
      function parseItalianNumber(input) {{
        const normalized = input.value.trim().replace(',', '.');
        if (!/^-?\\d+(?:\\.\\d+)?$/.test(normalized)) return null;
        const value = Number(normalized);
        const min = Number(input.dataset.min);
        const max = Number(input.dataset.max);
        return Number.isFinite(value) && value >= min && value <= max ? value : null;
      }}
      function formatItalianNumber(input) {{
        const value = parseItalianNumber(input);
        if (value !== null) input.value = value.toFixed(1).replace('.', ',');
      }}
      for (const input of document.querySelectorAll('input[inputmode="decimal"]')) {{
        input.value = input.value.replace('.', ',');
        input.addEventListener('input', () => {{
          const cursor = input.selectionStart;
          input.value = input.value.replace(/\\./g, ',').replace(/[^0-9,-]/g, '');
          if ((input.value.match(/,/g) || []).length > 1) {{
            const first = input.value.indexOf(',');
            input.value = input.value.slice(0, first + 1) + input.value.slice(first + 1).replace(/,/g, '');
          }}
          if (input.value.includes('-')) input.value = (input.value.startsWith('-') ? '-' : '') + input.value.replace(/-/g, '');
          input.setSelectionRange(Math.min(cursor, input.value.length), Math.min(cursor, input.value.length));
        }});
        input.addEventListener('blur', () => formatItalianNumber(input));
      }}
      document.getElementById('auto').addEventListener('click', async () => {{
        const snapshot = await fetch(endpoint + '/calibration-snapshot', {{method:'POST'}});
        if (!snapshot.ok) {{ alert(await errorMessage(snapshot)); return; }}
        if (!confirm('Usare i valori di pitch e roll appena acquisiti come nuova calibrazione?')) return;
        const response = await fetch(endpoint + '/calibration-form', {{method:'POST'}});
        if (!response.ok) {{ alert(await errorMessage(response)); }}
      }});
      async function applyManual(axis) {{
        const input = document.getElementById(axis);
        const value = parseItalianNumber(input);
        if (value === null) {{ alert('Inserisci un valore valido'); return; }}
        formatItalianNumber(input);
        const label = axis === 'pitch' ? 'Pitch' : 'Roll';
        if (!confirm(`Impostare manualmente ${{label}} a ${{value.toFixed(1).replace('.', ',')}}°?`)) return;
        const payload = axis === 'pitch' ? {{pitch_deg:value}} : {{roll_deg:value}};
        const response = await fetch(endpoint + '/manual-calibration', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
        if (!response.ok) {{ alert(await errorMessage(response)); }}
      }}
      document.getElementById('apply-pitch').addEventListener('click', () => applyManual('pitch'));
      document.getElementById('apply-roll').addEventListener('click', () => applyManual('roll'));
    </script></body></html>
    """, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@grafana_pages_router.get(
    "/api/v1/grafana/patients/{patient_code}/alert-session-control",
    response_class=HTMLResponse,
)
def grafana_alert_session_control(
    patient_code: str,
    alert_day_start: str = "",
    session_id: str = "",
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    accessible_patient_by_code(user, patient_code)
    sessions = influx_manager.query_day_sessions(patient_code) if influx_manager else []
    local_zone = ZoneInfo("Europe/Rome")
    choices = []
    for item in sessions:
        start = datetime.fromisoformat(item["start"])
        stop = datetime.fromisoformat(item["stop"])
        local_start = start.astimezone(local_zone)
        local_stop = stop.astimezone(local_zone)
        label = f'{local_start.strftime("%d/%m/%y %H:%M:%S")} – {local_stop.strftime("%H:%M:%S")}'
        choices.append((label, item["session_id"], item["start"], item["stop"]))
    safe_current = html.escape(session_id, quote=True)
    options = "".join(
        f'<option value="{html.escape(value, quote=True)}" data-start="{html.escape(start, quote=True)}" data-stop="{html.escape(stop, quote=True)}"'
        f'{" selected" if value == session_id else ""}>'
        f'{html.escape(label)}</option>'
        for label, value, start, stop in choices
    )
    empty = '<option value="">Nessuna sessione disponibile</option>' if not choices else ""
    return HTMLResponse(f"""
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <style>
      *{{box-sizing:border-box}} body{{margin:0;background:#111217;color:#f2f4f7;font:15px system-ui,sans-serif}}
      main{{height:100%;min-height:118px;padding:14px 18px;border:1px solid #34373d;border-radius:10px;background:#181b1f}}
      h2{{font-size:17px;margin:0 0 12px}} .controls{{display:grid;grid-template-columns:minmax(220px,1fr) minmax(300px,2fr);gap:12px}}
      label{{display:block;margin-bottom:6px;color:#c7c9d1;font-size:13px;font-weight:700}}
      input,select{{width:100%;height:42px;border:1px solid #475467;border-radius:7px;background:#111217;color:#fff;padding:0 12px;font-size:15px;outline:none}}
      input:focus,select:focus{{border-color:#5794f2;box-shadow:0 0 0 2px rgba(87,148,242,.2)}}
      @media(max-width:650px){{.controls{{grid-template-columns:1fr}}}}
    </style></head><body><main>
      <h2>Storico per sessione</h2>
      <div class="controls">
        <div><label for="search">Cerca per data o ora</label><input id="search" type="search" placeholder="Es. 20/07/26 oppure 10:30"></div>
        <div><label for="sessions">Sessione selezionata</label><select id="sessions">{options}{empty}</select></div>
      </div>
    </main><script>
      const select = document.getElementById('sessions');
      const search = document.getElementById('search');
      const original = [...select.options].map(option => ({{value:option.value,start:option.dataset.start || '',stop:option.dataset.stop || '',text:option.text}}));
      function render(filter='') {{
        const selected = select.value || '{safe_current}';
        const needle = filter.trim().toLocaleLowerCase('it');
        select.replaceChildren(...original.filter(option => !needle || option.text.toLocaleLowerCase('it').includes(needle)).map(option => {{
          const node = new Option(option.text, option.value, false, option.value === selected);
          node.dataset.start = option.start;
          node.dataset.stop = option.stop; return node;
        }}));
      }}
      render();
      function choose(value, start, stop) {{
        if (!value || !start || !stop) return;
        const url = new URL(window.parent.location.href);
        url.searchParams.set('var-session_id', value);
        url.searchParams.set('var-alert_day_start', start);
        url.searchParams.set('var-alert_day_stop', stop);
        url.searchParams.set('from', String(Date.parse(start)));
        url.searchParams.set('to', String(Date.parse(stop)));
        url.searchParams.delete('var-session_filter');
        window.parent.location.assign(url.toString());
      }}
      if (original.length && !original.some(option => option.value === '{safe_current}')) {{
        choose(original[0].value, original[0].start, original[0].stop);
      }}
      search.addEventListener('input', () => render(search.value));
      select.addEventListener('change', () => choose(select.value, select.selectedOptions[0].dataset.start, select.selectedOptions[0].dataset.stop));
    </script></body></html>
    """, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@grafana_pages_router.get(
    "/api/v1/grafana/patients/{patient_code}/night-monitoring/control",
    response_class=HTMLResponse,
)
def grafana_night_monitoring_control(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    """Compact doctor control embedded in the Grafana night dashboard."""
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    session = active_night_session(patient["id"])
    active = session is not None
    safe_patient = html.escape(patient_code, quote=True)
    session_time_sync = ""
    if session is not None:
        started_at = datetime.fromisoformat(str(session["started_at"]))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        session_start_ms = int(started_at.timestamp() * 1000)
        safe_session_id = html.escape(str(session["id"]), quote=True)
        session_time_sync = f"""
        <script>
          (() => {{
            if (window.parent === window) return;
            const dashboardUrl = new URL(window.parent.location.href);
            if (dashboardUrl.searchParams.get('night-session') === '{safe_session_id}') return;
            dashboardUrl.searchParams.set('from', '{session_start_ms}');
            dashboardUrl.searchParams.set('to', 'now');
            dashboardUrl.searchParams.set('night-session', '{safe_session_id}');
            window.parent.location.replace(dashboardUrl.toString());
          }})();
        </script>
        """
    action = "stop" if active else "start"
    button_text = "DISATTIVA MOD. NOTTE" if active else "ATTIVA MOD. NOTTE"
    button_color = "#b42318" if active else "#3274d9"
    confirmation = (
        "Terminare la modalità notte per questo paziente?"
        if active
        else "Attivare la modalità notte per questo paziente?"
    )
    return HTMLResponse(f"""
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <style>
      *{{box-sizing:border-box}} body{{margin:0;background:#181b1f;color:#f2f4f7;font:15px system-ui,sans-serif}}
      main{{min-height:86px;display:flex;align-items:center;justify-content:center;padding:14px 20px}}
      button{{min-width:270px;padding:14px 22px;border:0;border-radius:9px;background:{button_color};color:white;font-weight:800;font-size:16px;cursor:pointer;white-space:nowrap}}
      @media(max-width:650px){{button{{width:100%;min-width:0}}}}
    </style></head><body><main>
      <form method="post" action="/api/v1/grafana/patients/{safe_patient}/night-monitoring/{action}"
        onsubmit="return confirm('{confirmation}')">
        <button type="submit">{button_text}</button>
      </form>
    </main>{session_time_sync}</body></html>
    """)


@grafana_pages_router.get(
    "/api/v1/grafana/patients/{patient_code}/night-session-control",
    response_class=HTMLResponse,
)
def grafana_night_session_control(
    patient_code: str,
    session_id: str = "",
    smartback_grafana_session: str | None = Cookie(default=None),
):
    """Searchable session selector embedded in the night-history dashboard."""
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    rows = auth_db.execute(
        "SELECT id,started_at,ended_at FROM night_monitoring_sessions "
        "WHERE patient_id=? ORDER BY started_at DESC LIMIT 200",
        (patient["id"],),
    ).fetchall()
    local_zone = ZoneInfo("Europe/Rome")
    choices: list[tuple[str, str, str, str]] = []
    for row in rows:
        start = datetime.fromisoformat(str(row["started_at"]))
        stop = (
            datetime.fromisoformat(str(row["ended_at"]))
            if row["ended_at"]
            else datetime.now(timezone.utc)
        )
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if stop.tzinfo is None:
            stop = stop.replace(tzinfo=timezone.utc)
        local_start = start.astimezone(local_zone)
        local_stop = stop.astimezone(local_zone)
        label = (
            f'{local_start.strftime("%d/%m/%y %H:%M:%S")} – '
            f'{local_stop.strftime("%H:%M:%S")}'
        )
        choices.append((label, str(row["id"]), start.isoformat(), stop.isoformat()))

    safe_current = html.escape(session_id, quote=True)
    options = "".join(
        f'<option value="{html.escape(value, quote=True)}" '
        f'data-start="{html.escape(start, quote=True)}" '
        f'data-stop="{html.escape(stop, quote=True)}"'
        f'{" selected" if value == session_id else ""}>'
        f'{html.escape(label)}</option>'
        for label, value, start, stop in choices
    )
    empty = '<option value="">Nessuna sessione disponibile</option>' if not choices else ""
    return HTMLResponse(f"""
    <!doctype html><html lang="it"><head><meta charset="utf-8">
    <style>
      *{{box-sizing:border-box}} body{{margin:0;background:#111217;color:#f2f4f7;font:15px system-ui,sans-serif}}
      main{{height:100%;min-height:118px;padding:14px 18px;border:1px solid #34373d;border-radius:10px;background:#181b1f}}
      h2{{font-size:17px;margin:0 0 12px}} .controls{{display:grid;grid-template-columns:minmax(220px,1fr) minmax(300px,2fr);gap:12px}}
      label{{display:block;margin-bottom:6px;color:#c7c9d1;font-size:13px;font-weight:700}}
      input,select{{width:100%;height:42px;border:1px solid #475467;border-radius:7px;background:#111217;color:#fff;padding:0 12px;font-size:15px;outline:none}}
      input:focus,select:focus{{border-color:#5794f2;box-shadow:0 0 0 2px rgba(87,148,242,.2)}}
      @media(max-width:650px){{.controls{{grid-template-columns:1fr}}}}
    </style></head><body><main>
      <h2>Storico per sessione</h2>
      <div class="controls">
        <div><label for="search">Cerca per data o ora</label><input id="search" type="search" placeholder="Es. 21/07/26 oppure 02:30"></div>
        <div><label for="sessions">Sessione selezionata</label><select id="sessions">{options}{empty}</select></div>
      </div>
    </main><script>
      const select = document.getElementById('sessions');
      const search = document.getElementById('search');
      const original = [...select.options].map(option => ({{value:option.value,start:option.dataset.start || '',stop:option.dataset.stop || '',text:option.text}}));
      function render(filter='') {{
        const selected = select.value || '{safe_current}';
        const needle = filter.trim().toLocaleLowerCase('it');
        select.replaceChildren(...original.filter(option => !needle || option.text.toLocaleLowerCase('it').includes(needle)).map(option => {{
          const node = new Option(option.text, option.value, false, option.value === selected);
          node.dataset.start = option.start; node.dataset.stop = option.stop; return node;
        }}));
      }}
      function choose(value, start, stop) {{
        if (!value || !start || !stop) return;
        const url = new URL(window.parent.location.href);
        url.searchParams.set('var-session_id', value);
        url.searchParams.set('from', String(Date.parse(start)));
        url.searchParams.set('to', String(Date.parse(stop)));
        window.parent.location.assign(url.toString());
      }}
      render();
      if (original.length && !original.some(option => option.value === '{safe_current}')) {{
        choose(original[0].value, original[0].start, original[0].stop);
      }}
      search.addEventListener('input', () => render(search.value));
      select.addEventListener('change', () => choose(select.value, select.selectedOptions[0].dataset.start, select.selectedOptions[0].dataset.stop));
    </script></body></html>
    """, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@grafana_router.post("/api/v1/grafana/patients/{patient_code}/night-monitoring/start")
def grafana_start_night_monitoring(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    _start_night_session(patient, user)
    return RedirectResponse(
        url=f"/api/v1/grafana/patients/{patient_code}/night-monitoring/control",
        status_code=303,
    )


@grafana_router.post("/api/v1/grafana/patients/{patient_code}/night-monitoring/stop")
def grafana_stop_night_monitoring(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    _stop_night_session(patient, end_reason="doctor")
    return RedirectResponse(
        url=f"/api/v1/grafana/patients/{patient_code}/night-monitoring/control",
        status_code=303,
    )


@grafana_pages_router.get("/grafana-calibration", response_class=HTMLResponse)
def grafana_calibration_page(
    patient_id: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_id)
    current = auth_db.execute(
        "SELECT reference_pitch_deg,reference_roll_deg,calibrated_at "
        "FROM device_calibrations WHERE patient_id=? AND algorithm_version=? "
        "ORDER BY calibrated_at DESC LIMIT 1",
        (patient["id"], CALIBRATION_ALGORITHM_VERSION),
    ).fetchone()
    safe_patient = html.escape(patient_id, quote=True)
    if current is None:
        current_reference = "Nessuna calibrazione salvata"
    else:
        current_reference = (
            f"Pitch {float(current['reference_pitch_deg']):.1f}° · "
            f"Roll {float(current['reference_roll_deg']):.1f}°"
        )
    return f"""
    <main style="max-width:620px;margin:6vh auto;padding:30px;font-family:system-ui,sans-serif;line-height:1.45">
      <a href="/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id={safe_patient}&refresh=1s"
         style="color:#3274d9;text-decoration:none">← Torna al monitoraggio</a>
      <h1 style="margin-top:28px">Calibrazione posturale</h1>
      <section style="padding:18px;border:1px solid #d0d5dd;border-radius:10px;margin:20px 0">
        <strong>Paziente:</strong> {safe_patient}<br>
        <strong>Riferimento attuale:</strong> {html.escape(current_reference)}
      </section>
      <section style="padding:18px;background:#fff4e5;border-left:5px solid #f79009;border-radius:6px">
        <strong>Attenzione</strong>
        <p style="margin-bottom:0">La nuova calibrazione sostituirà lo zero corrente di pitch e roll.
        Il paziente deve essere fermo, in postura neutra, e la maglia deve risultare ON.</p>
      </section>
      <label style="display:flex;gap:12px;align-items:flex-start;margin:24px 0;font-weight:600">
        <input id="ack" type="checkbox" style="width:20px;height:20px;margin-top:2px">
        Ho preso visione: la calibrazione corrente verrà sostituita.
      </label>
      <button id="confirm" disabled
        style="width:100%;padding:14px;border:0;border-radius:8px;background:#b8c0cc;color:white;font-size:17px;font-weight:700;cursor:not-allowed">
        CONFERMA CALIBRAZIONE
      </button>
      <p id="result" role="status" style="min-height:1.5em;font-weight:600"></p>
      <script>
        const ack = document.getElementById("ack");
        const confirmButton = document.getElementById("confirm");
        const result = document.getElementById("result");
        ack.addEventListener("change", () => {{
          confirmButton.disabled = !ack.checked;
          confirmButton.style.background = ack.checked ? "#3274d9" : "#b8c0cc";
          confirmButton.style.cursor = ack.checked ? "pointer" : "not-allowed";
        }});
        confirmButton.addEventListener("click", async () => {{
          if (!ack.checked) return;
          confirmButton.disabled = true;
          result.textContent = "";
          const response = await fetch(
            "/api/v1/grafana/patients/" + encodeURIComponent("{safe_patient}") + "/calibration",
            {{method: "POST", headers: {{"Content-Type": "application/json"}}, body: JSON.stringify({{confirmed: true}})}}
          );
          const body = await response.json().catch(() => ({{}}));
          if (!response.ok) {{
            result.style.color = "#b42318";
            result.textContent = body.detail || "Calibrazione non riuscita";
            confirmButton.disabled = false;
            return;
          }}
          setTimeout(() => {{
            window.location.href = "/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id={safe_patient}&refresh=1s";
          }}, 900);
        }});
      </script>
    </main>
    """


@grafana_router.post("/api/v1/grafana/logout", status_code=204)
def grafana_logout(
    response: Response,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    if smartback_grafana_session:
        auth_db.execute("DELETE FROM sessions WHERE token=?", (smartback_grafana_session,))
        auth_db.commit()
    response.delete_cookie(GRAFANA_SESSION_COOKIE, path="/")
    response.headers["Clear-Site-Data"] = '"cookies"'
    response.headers["Cache-Control"] = "no-store"


@grafana_pages_router.get("/grafana-logout")
def grafana_browser_logout(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    if smartback_grafana_session:
        auth_db.execute("DELETE FROM sessions WHERE token=?", (smartback_grafana_session,))
        auth_db.commit()
    response = RedirectResponse(url="/grafana-login", status_code=303)
    response.delete_cookie(GRAFANA_SESSION_COOKIE, path="/")
    response.headers["Clear-Site-Data"] = '"cookies"'
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_router.get("/api/v1/auth/me")
def me(user: sqlite3.Row = Depends(current_user)):
    return public_user(user)


@auth_router.post("/api/v1/auth/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        auth_db.execute("DELETE FROM sessions WHERE token=?", (authorization.removeprefix("Bearer ").strip(),))
        auth_db.commit()


@auth_router.put("/api/v1/auth/password", status_code=204)
def change_password(body: ChangePasswordRequest, user: sqlite3.Row = Depends(current_user)):
    current_digest, _ = hash_password(body.current_password, bytes.fromhex(user["password_salt"]))
    if not hmac.compare_digest(current_digest, user["password_hash"]):
        raise HTTPException(status_code=400, detail="La password attuale non è corretta")
    new_digest, new_salt = hash_password(body.new_password)
    auth_db.execute(
        "UPDATE users SET password_hash=?, password_salt=? WHERE id=?",
        (new_digest, new_salt, user["id"]),
    )
    auth_db.commit()


@auth_router.put("/api/v1/auth/avatar")
def change_avatar(body: AvatarRequest, user: sqlite3.Row = Depends(current_user)):
    auth_db.execute("UPDATE users SET avatar_data=? WHERE id=?", (body.avatar_data, user["id"]))
    auth_db.commit()
    updated_user = auth_db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return public_user(updated_user)


@doctor_router.get("/api/v1/doctor/patients")
def doctor_patients(user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato a medici e fisioterapisti")
    rows = auth_db.execute(
        "SELECT patients.*, links.created_at AS associated_at "
        "FROM doctor_patients links JOIN users patients ON patients.id=links.patient_id "
        "WHERE links.doctor_id=? ORDER BY patients.name COLLATE NOCASE",
        (user["id"],),
    ).fetchall()
    latest_posture = mqtt_handler.latest_posture if mqtt_handler else None
    current_patient_code = latest_posture.get("patient_id") if latest_posture else None
    return {"items": [{
        **public_user(row), "associated_at": row["associated_at"],
        "has_live_data": row["patient_code"] == current_patient_code,
    } for row in rows], "count": len(rows)}


@doctor_router.post("/api/v1/doctor/patients", status_code=201)
def associate_patient(body: AssociatePatientRequest, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato a medici e fisioterapisti")
    patient = auth_db.execute(
        "SELECT * FROM users WHERE fiscal_code=? AND role='patient'", (body.fiscal_code,)
    ).fetchone()
    if patient is None:
        raise HTTPException(status_code=404, detail="Nessun paziente registrato con questo codice fiscale")
    try:
        auth_db.execute(
            "INSERT INTO doctor_patients(doctor_id,patient_id,created_at) VALUES (?,?,?)",
            (user["id"], patient["id"], datetime.now(timezone.utc).isoformat()),
        )
        auth_db.commit()
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Paziente già associato") from None
    latest_posture = mqtt_handler.latest_posture if mqtt_handler else None
    return {
        **public_user(patient),
        "has_live_data": bool(
            latest_posture and patient["patient_code"] == latest_posture.get("patient_id")
        ),
    }


@system_router.get("/health")
def health():
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


@day_monitoring_router.get("/api/v1/posture/latest")
def get_latest_posture():
    latest = mqtt_handler.latest_posture if mqtt_handler else None
    if latest is None:
        raise HTTPException(status_code=404, detail="Nessun campione posturale ancora ricevuto")
    return latest


@devices_router.get("/api/v1/device/latest")
def get_latest_device():
    latest = mqtt_handler.latest_device if mqtt_handler else None
    if latest is None:
        raise HTTPException(status_code=404, detail="Nessuno stato del dispositivo ancora ricevuto")
    return latest


@devices_router.post("/api/v1/devices/{device_id}/calibration")
def calibrate(device_id: str, user: sqlite3.Row = Depends(current_user)):
    if mqtt_handler is None:
        raise HTTPException(status_code=503, detail="Motore posturale non disponibile")
    sample = fresh_posture_sample(
        str(mqtt_handler.latest_posture.get("patient_id"))
        if mqtt_handler.latest_posture
        else "",
        device_id,
    )
    return calibrate_patient_device(
        user=user,
        patient_code=str(sample["patient_id"]),
        device_id=device_id,
    )


def query_posture_history(patient_code: str, minutes: int, limit: int = 600) -> list[dict[str, Any]]:
    if influx_manager is None:
        raise HTTPException(status_code=503, detail="Archivio temporale non disponibile")
    return influx_manager.query_posture_history(
        patient_code,
        minutes,
        threshold_profile_for_patient_code(patient_code),
        limit,
    )


def _night_session_duration_seconds(row: sqlite3.Row) -> int:
    started_at = datetime.fromisoformat(str(row["started_at"]))
    ended_at = (
        datetime.fromisoformat(str(row["ended_at"]))
        if row["ended_at"]
        else datetime.now(timezone.utc)
    )
    return max(0, round((ended_at - started_at).total_seconds()))


def serialize_night_session(row: sqlite3.Row) -> dict[str, Any]:
    """Stable API contract for a night-monitoring session."""
    return {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "device_id": row["device_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "end_reason": row["end_reason"],
        "duration_seconds": _night_session_duration_seconds(row),
        "classifier_version": int(row["classifier_version"]),
        "summary": {
            "supine_seconds": float(row["supine_seconds"]),
            "prone_seconds": float(row["prone_seconds"]),
            "right_side_seconds": float(row["right_side_seconds"]),
            "left_side_seconds": float(row["left_side_seconds"]),
            "unknown_seconds": float(row["unknown_seconds"]),
            "position_changes": int(row["position_changes"]),
            "data_gap_seconds": float(row["data_gap_seconds"]),
        },
    }


def active_night_session(patient_id: str) -> sqlite3.Row | None:
    return auth_db.execute(
        "SELECT * FROM night_monitoring_sessions "
        "WHERE patient_id=? AND status='active' ORDER BY started_at DESC LIMIT 1",
        (patient_id,),
    ).fetchone()


def _require_patient(user: sqlite3.Row) -> None:
    if user["role"] != "patient":
        raise HTTPException(
            status_code=403,
            detail="La modalità notturna può essere attivata o fermata solo dal paziente",
        )


def _start_night_session(patient: sqlite3.Row, actor: sqlite3.Row) -> dict[str, Any]:
    """Start one session for a patient after the caller authorization check."""
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        if active_night_session(patient["id"]) is not None:
            raise HTTPException(status_code=409, detail="Monitoraggio notturno già attivo")
        assignment = auth_db.execute(
            "SELECT assignments.device_id,devices.source_type FROM device_assignments assignments "
            "JOIN devices ON devices.device_id=assignments.device_id "
            "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
            "AND devices.archived_at IS NULL LIMIT 1",
            (patient["id"],),
        ).fetchone()
        if assignment is None:
            raise HTTPException(
                status_code=409,
                detail="Nessuna maglia attiva assegnata al paziente",
            )
        sortable_start = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        session_id = f"night_{sortable_start}_{secrets.token_hex(6)}"
        try:
            auth_db.execute(
                "INSERT INTO night_monitoring_sessions("
                "id,patient_id,device_id,status,started_at,created_by) "
                "VALUES (?,?,?,'active',?,?)",
                (session_id, patient["id"], assignment["device_id"], now, actor["id"]),
            )
            auth_db.commit()
        except sqlite3.IntegrityError:
            auth_db.rollback()
            raise HTTPException(
                status_code=409,
                detail="La maglia è già impegnata in un monitoraggio notturno",
            ) from None
    session = auth_db.execute(
        "SELECT * FROM night_monitoring_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if influx_manager is not None:
        influx_manager.persist_night_session_state(
            patient_code=str(patient["patient_code"]),
            session_id=str(session_id),
            device_id=str(assignment["device_id"]),
            active=True,
        )
    if assignment["source_type"] == "simulated" and mqtt_handler:
        mqtt_handler.publish_simulation_scenario(str(assignment["device_id"]), "night-cycle")
    return {"mode": "night", "active": True, "session": serialize_night_session(session)}


def _stop_night_session(
    patient: sqlite3.Row,
    *,
    end_reason: str,
) -> dict[str, Any]:
    """Stop the active patient session and restore simulated daytime data."""
    with database_lock:
        session = active_night_session(patient["id"])
        if session is None:
            raise HTTPException(status_code=409, detail="Nessun monitoraggio notturno attivo")
        ended_at = datetime.now(timezone.utc).isoformat()
        auth_db.execute(
            "UPDATE night_monitoring_sessions SET status='completed',ended_at=?,end_reason=? "
            "WHERE id=? AND status='active'",
            (ended_at, end_reason, session["id"]),
        )
        auth_db.commit()
    completed = auth_db.execute(
        "SELECT * FROM night_monitoring_sessions WHERE id=?", (session["id"],)
    ).fetchone()
    device = auth_db.execute(
        "SELECT source_type FROM devices WHERE device_id=?", (session["device_id"],)
    ).fetchone()
    if influx_manager is not None:
        influx_manager.persist_night_session_state(
            patient_code=str(patient["patient_code"]),
            session_id=str(session["id"]),
            device_id=str(session["device_id"]),
            active=False,
        )
    if device and device["source_type"] == "simulated" and mqtt_handler:
        mqtt_handler.publish_simulation_scenario(str(session["device_id"]), "day-cycle")
    return {"mode": "day", "active": False, "session": serialize_night_session(completed)}


@night_monitoring_router.post("/api/v1/night-monitoring/start", status_code=201)
def start_night_monitoring(user: sqlite3.Row = Depends(current_user)):
    _require_patient(user)
    return _start_night_session(user, user)


@night_monitoring_router.post("/api/v1/night-monitoring/stop")
def stop_night_monitoring(user: sqlite3.Row = Depends(current_user)):
    _require_patient(user)
    return _stop_night_session(user, end_reason="patient")


@night_monitoring_router.get("/api/v1/night-monitoring/status")
def night_monitoring_status(
    patient_id: str | None = None,
    user: sqlite3.Row = Depends(current_user),
):
    patient = accessible_patient(user, patient_id)
    session = active_night_session(patient["id"])
    return {
        "mode": "night" if session else "day",
        "active": session is not None,
        "session": serialize_night_session(session) if session else None,
    }


@night_monitoring_router.get("/api/v1/night-monitoring/history")
def night_monitoring_history(
    patient_id: str | None = None,
    limit: int = 50,
    user: sqlite3.Row = Depends(current_user),
):
    patient = accessible_patient(user, patient_id)
    normalized_limit = min(max(limit, 1), 200)
    rows = auth_db.execute(
        "SELECT * FROM night_monitoring_sessions WHERE patient_id=? "
        "ORDER BY started_at DESC LIMIT ?",
        (patient["id"], normalized_limit),
    ).fetchall()
    return {
        "patient_id": patient["id"],
        "patient_code": patient["patient_code"],
        "items": [serialize_night_session(row) for row in rows],
        "count": len(rows),
    }


@night_monitoring_router.get("/api/v1/night-monitoring/history/summary")
def night_monitoring_history_summary(
    patient_id: str | None = None,
    user: sqlite3.Row = Depends(current_user),
):
    """Return totals across every persisted, completed night session."""
    patient = accessible_patient(user, patient_id)
    row = auth_db.execute(
        "SELECT COUNT(*) AS session_count,"
        "COALESCE(SUM(supine_seconds),0) AS supine_seconds,"
        "COALESCE(SUM(prone_seconds),0) AS prone_seconds,"
        "COALESCE(SUM(right_side_seconds),0) AS right_side_seconds,"
        "COALESCE(SUM(left_side_seconds),0) AS left_side_seconds,"
        "COALESCE(SUM(unknown_seconds),0) AS unknown_seconds,"
        "COALESCE(SUM(position_changes),0) AS position_changes,"
        "COALESCE(SUM(data_gap_seconds),0) AS data_gap_seconds "
        "FROM night_monitoring_sessions WHERE patient_id=? AND status!='active'",
        (patient["id"],),
    ).fetchone()
    return {
        "patient_id": patient["id"],
        "patient_code": patient["patient_code"],
        "session_count": int(row["session_count"]),
        "summary": {
            "supine_seconds": float(row["supine_seconds"]),
            "prone_seconds": float(row["prone_seconds"]),
            "right_side_seconds": float(row["right_side_seconds"]),
            "left_side_seconds": float(row["left_side_seconds"]),
            "unknown_seconds": float(row["unknown_seconds"]),
            "position_changes": int(row["position_changes"]),
            "data_gap_seconds": float(row["data_gap_seconds"]),
        },
    }


@night_monitoring_router.get("/api/v1/night-monitoring/sessions/{session_id}")
def night_monitoring_session(
    session_id: str,
    user: sqlite3.Row = Depends(current_user),
):
    row = auth_db.execute(
        "SELECT * FROM night_monitoring_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Sessione notturna non trovata")
    accessible_patient(user, row["patient_id"])
    result = serialize_night_session(row)
    result["positions"] = (
        influx_manager.query_night_positions(session_id) if influx_manager else []
    )
    return result


def normalize_history_range(
    *,
    minutes: int,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime, int]:
    requested_end = end or datetime.now(timezone.utc)
    if requested_end.tzinfo is None:
        requested_end = requested_end.replace(tzinfo=timezone.utc)
    requested_end = requested_end.astimezone(timezone.utc)
    if start is None:
        normalized_minutes = min(max(minutes, 1), 527_040)
        requested_start = requested_end - timedelta(minutes=normalized_minutes)
    else:
        requested_start = (
            start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)
        )
        normalized_minutes = max(1, math.ceil((requested_end - requested_start).total_seconds() / 60))
    if requested_start >= requested_end:
        raise HTTPException(status_code=422, detail="L'inizio dello storico deve precedere la fine")
    if requested_end - requested_start > timedelta(days=366):
        raise HTTPException(status_code=422, detail="L'intervallo massimo consultabile e di 366 giorni")
    return requested_start, requested_end, normalized_minutes


@day_monitoring_router.get("/api/v1/posture/history")
def posture_history(
    minutes: int = 60,
    patient_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 600,
    user: sqlite3.Row = Depends(current_user),
):
    patient = accessible_patient(user, patient_id)
    if influx_manager is None:
        raise HTTPException(status_code=503, detail="Archivio temporale non disponibile")
    requested_start, requested_end, normalized_minutes = normalize_history_range(
        minutes=minutes, start=start, end=end
    )
    result = influx_manager.query_posture_history_details(
        patient["patient_code"],
        start=requested_start,
        end=requested_end,
        profile=threshold_profile_for_patient(patient),
        limit=limit,
        stale_seconds=DATA_STALE_SECONDS,
    )
    return {
        **result,
        "minutes": normalized_minutes,
        "patient_id": patient["id"],
        "patient_code": patient["patient_code"],
    }


@day_monitoring_router.get("/api/v1/posture/history/availability")
def posture_history_availability(
    patient_id: str | None = None,
    user: sqlite3.Row = Depends(current_user),
):
    patient = accessible_patient(user, patient_id)
    if influx_manager is None:
        raise HTTPException(status_code=503, detail="Archivio temporale non disponibile")
    return {
        **influx_manager.query_posture_availability(patient["patient_code"]),
        "patient_id": patient["id"],
        "patient_code": patient["patient_code"],
    }


@day_monitoring_router.get("/api/v1/posture/history/sessions")
def posture_history_sessions(
    patient_id: str | None = None,
    user: sqlite3.Row = Depends(current_user),
):
    """Return the daytime sessions available to the authenticated viewer."""
    patient = accessible_patient(user, patient_id)
    if influx_manager is None:
        raise HTTPException(status_code=503, detail="Archivio temporale non disponibile")
    return {
        "items": influx_manager.query_day_sessions(patient["patient_code"]),
        "patient_id": patient["id"],
        "patient_code": patient["patient_code"],
    }


@day_monitoring_router.get("/api/v1/patient/statistics")
def patient_statistics(minutes: int = 60, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Le statistiche personali sono riservate al paziente")
    rows = query_posture_history(user["patient_code"], minutes)
    count = len(rows)
    incorrect = sum(1 for row in rows if row["is_incorrect"])
    absolute_values = [abs(float(row["deviation_deg"])) for row in rows]
    return {
        "period_minutes": min(max(minutes, 1), 10080),
        "samples": count,
        "correct_percentage": round((count - incorrect) * 100 / count, 1) if count else 0,
        "incorrect_percentage": round(incorrect * 100 / count, 1) if count else 0,
        "average_deviation_deg": round(sum(absolute_values) / count, 1) if count else 0,
        "maximum_deviation_deg": round(max(absolute_values), 1) if count else 0,
    }


@doctor_router.get("/api/v1/doctor/patients/{patient_id}/monitoring-config")
def get_monitoring_config(patient_id: str, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    patient = accessible_patient(user, patient_id)
    return monitoring_config_for_patient(patient)


@doctor_router.put("/api/v1/doctor/patients/{patient_id}/monitoring-config")
def update_monitoring_config(
    patient_id: str,
    body: MonitoringConfigRequest,
    user: sqlite3.Row = Depends(current_user),
):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    patient = accessible_patient(user, patient_id)
    auth_db.execute(
        "INSERT INTO monitoring_configs("
        "patient_id,moderate_deviation_deg,marked_deviation_deg,moderate_roll_deg,marked_roll_deg,"
        "persistence_seconds,updated_at,updated_by) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET "
        "moderate_deviation_deg=excluded.moderate_deviation_deg,"
        "marked_deviation_deg=excluded.marked_deviation_deg,"
        "moderate_roll_deg=excluded.moderate_roll_deg,"
        "marked_roll_deg=excluded.marked_roll_deg,"
        "persistence_seconds=excluded.persistence_seconds,"
        "updated_at=excluded.updated_at,updated_by=excluded.updated_by",
        (
            patient["id"],
            body.moderate_deviation_deg,
            body.marked_deviation_deg,
            body.moderate_roll_deg,
            body.marked_roll_deg,
            body.persistence_seconds,
            datetime.now(timezone.utc).isoformat(),
            user["id"],
        ),
    )
    auth_db.commit()
    return monitoring_config_for_patient(patient)


@doctor_router.delete("/api/v1/doctor/patients/{patient_id}/monitoring-config")
def reset_monitoring_config(patient_id: str, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    patient = accessible_patient(user, patient_id)
    auth_db.execute("DELETE FROM monitoring_configs WHERE patient_id=?", (patient["id"],))
    auth_db.commit()
    return monitoring_config_for_patient(patient)


@realtime_router.websocket("/ws/wearable")
async def wearable_stream(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    requested_patient_id = websocket.query_params.get("patient_id")
    user = user_for_session(token) if token else None
    if user is None:
        await websocket.close(code=4401, reason="Sessione richiesta")
        return
    try:
        patient = accessible_patient(user, requested_patient_id)
    except HTTPException:
        await websocket.close(code=4403, reason="Paziente non autorizzato")
        return
    patient_code = str(patient["patient_code"])
    websockets[websocket] = patient_code
    try:
        latest = mqtt_handler.latest_posture if mqtt_handler else None
        if latest and str(latest.get("patient_id")) == patient_code:
            await websocket.send_json(latest)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websockets.pop(websocket, None)


# Route registration stays at the end because FastAPI copies a router's routes
# when it is included. Keeping the list explicit makes consumer boundaries
# visible and prevents Grafana-only endpoints from blending into app APIs.
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(doctor_router)
app.include_router(day_monitoring_router)
app.include_router(night_monitoring_router)
app.include_router(devices_router)
app.include_router(grafana_router)
app.include_router(grafana_pages_router)
app.include_router(realtime_router)


def italian_openapi_schema() -> dict[str, Any]:
    """Generate the public contract with Italian human-facing labels."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    for (method, path), summary in OPENAPI_SUMMARIES.items():
        operation = schema.get("paths", {}).get(path, {}).get(method)
        if operation is not None:
            operation["summary"] = summary
    app.openapi_schema = schema
    return schema


app.openapi = italian_openapi_schema
