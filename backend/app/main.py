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
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import (
    ALERT_TOPIC, AUTH_DB_PATH, DATA_STALE_SECONDS, DEVICE_TOPIC,
    GRAFANA_ADMIN_PASSWORD, GRAFANA_ADMIN_USER, INFLUX_BUCKET,
    INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL, MARKED_DEVIATION_DEG,
    MARKED_ROLL_DEG, MEDICAL_REGISTRATION_CODE, MODERATE_DEVIATION_DEG,
    MODERATE_ROLL_DEG, MQTT_HOST, MQTT_PORT, PERSISTENCE_SECONDS,
    POSTURE_EMA_ALPHA, POSTURE_HYSTERESIS_DEG, POSTURE_TOPIC,
)
from app.database import init_database
from app.influx_manager import InfluxManager
from app.mqtt_handler import SmartBackMqttHandler
from app.posture_service import PostureEngine, ThresholdProfile
EMAIL_DOMAIN_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)
GRAFANA_SESSION_COOKIE = "smartback_grafana_session"
CALIBRATION_ALGORITHM_VERSION = 2

websockets: set[WebSocket] = set()
influx_manager: InfluxManager | None = None
posture_engine: PostureEngine | None = None
mqtt_handler: SmartBackMqttHandler | None = None
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
    device_id: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
            raise ValueError("L'identificativo può contenere lettere, numeri, _ e -")
        return normalized

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


def public_user(row: sqlite3.Row) -> dict[str, str | None]:
    return {
        "id": row["id"], "name": row["name"], "email": row["email"],
        "first_name": row["first_name"], "last_name": row["last_name"],
        "role": row["role"], "patient_code": row["patient_code"],
        "professional_verified": bool(row["professional_verified"]),
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
    # SQLite dedicata evita l'uso concorrente della connessione globale.
    with sqlite3.connect(AUTH_DB_PATH) as connection:
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
    if user is None:
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


async def broadcast(payload: dict[str, Any]) -> None:
    stale = []
    for socket in list(websockets):
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        websockets.discard(socket)


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
        "SELECT device_id FROM devices WHERE source_type='simulated' ORDER BY device_id"
    ).fetchall()
    return [str(row["device_id"]) for row in rows]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_handler, influx_manager, posture_engine, auth_db
    loop = asyncio.get_running_loop()
    auth_db = init_database(AUTH_DB_PATH)
    ensure_grafana_admin()
    influx_manager = InfluxManager(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
        bucket=INFLUX_BUCKET,
    )
    posture_engine = PostureEngine(
        threshold_profile_for_patient_code,
        ema_alpha=POSTURE_EMA_ALPHA,
        hysteresis_deg=POSTURE_HYSTERESIS_DEG,
        calibration_provider=stored_calibration_for_device,
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
    )
    mqtt_handler.start(loop)
    yield
    await mqtt_handler.stop()
    influx_manager.close()
    auth_db.close()


app = FastAPI(title="SmartBack API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "SmartBack API", "docs": "/docs", "health": "/health"}


@app.post("/api/v1/auth/register", status_code=201)
def register(body: RegisterRequest):
    role = body.role
    email = body.email.lower().strip()
    if auth_db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise HTTPException(status_code=409, detail="Utente già registrato")
    digest, salt = hash_password(body.password)
    user_id = f"usr_{secrets.token_hex(8)}"
    patient_code = f"patient-{user_id.removeprefix('usr_')}" if role == "patient" else None
    full_name = f"{body.first_name} {body.last_name}"
    try:
        auth_db.execute(
            "INSERT INTO users(id,name,first_name,last_name,email,password_hash,password_salt,role,created_at,patient_code,fiscal_code,professional_verified) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, full_name, body.first_name, body.last_name, email, digest, salt, role,
             datetime.now(timezone.utc).isoformat(), patient_code, body.fiscal_code, 1 if role == "doctor" else 0),
        )
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Email o codice fiscale già registrato") from None
    auth_db.commit()
    user = auth_db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return {"access_token": create_session(user_id), "user": public_user(user)}


@app.post("/api/v1/auth/login")
def login(body: LoginRequest):
    user = authenticate_user(str(body.email), body.password)
    return {"access_token": create_session(user["id"]), "user": public_user(user)}


@app.get("/grafana-login", response_class=HTMLResponse)
def grafana_login_page():
    return """
    <main style="max-width:420px;margin:8vh auto;padding:28px;font-family:system-ui,sans-serif">
      <h1 style="font-size:24px">SmartBack · Accesso medico</h1>
      <p>Accedi con le credenziali SmartBack verificate per il ruolo medico.</p>
      <form id="login" style="display:grid;gap:14px">
        <label>Email o amministratore <input id="email" type="text" autocomplete="username" required
          style="display:block;width:100%;box-sizing:border-box;padding:10px;margin-top:5px"></label>
        <label>Password
          <span style="display:flex;position:relative;margin-top:5px">
            <input id="password" type="password" autocomplete="current-password" required
              style="width:100%;box-sizing:border-box;padding:10px 46px 10px 10px">
            <button id="toggle-password" type="button" aria-label="Mostra password" title="Mostra password"
              style="position:absolute;right:2px;top:2px;bottom:2px;width:42px;border:0;background:transparent;cursor:pointer;font-size:20px">👁</button>
          </span>
        </label>
        <button type="submit" style="padding:11px;cursor:pointer">Accedi alla dashboard</button>
        <p id="error" role="alert" style="color:#b42318;min-height:1.4em"></p>
      </form>
      <script>
        const password = document.getElementById("password");
        const togglePassword = document.getElementById("toggle-password");
        togglePassword.addEventListener("click", () => {
          const reveal = password.type === "password";
          password.type = reveal ? "text" : "password";
          togglePassword.setAttribute("aria-label", reveal ? "Nascondi password" : "Mostra password");
          togglePassword.setAttribute("title", reveal ? "Nascondi password" : "Mostra password");
          togglePassword.textContent = reveal ? "🙈" : "👁";
        });
        document.getElementById("login").addEventListener("submit", async (event) => {
          event.preventDefault();
          const error = document.getElementById("error");
          error.textContent = "";
          const response = await fetch("/api/v1/grafana/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              email: document.getElementById("email").value,
              password: password.value
            })
          });
          if (response.ok) {
            const body = await response.json();
            window.location.assign(body.redirect || "/smartback/");
            return;
          }
          const body = await response.json().catch(() => ({}));
          error.textContent = body.detail || "Accesso non riuscito";
        });
      </script>
    </main>
    """


@app.post("/api/v1/grafana/login")
def grafana_login(body: GrafanaLoginRequest, response: Response):
    user = authenticate_grafana_user(body.email, body.password)
    if user["role"] != "doctor" or not bool(user["professional_verified"]):
        raise HTTPException(status_code=403, detail="Accesso riservato ai medici verificati")
    token = create_session(user["id"])
    response.set_cookie(
        GRAFANA_SESSION_COOKIE,
        token,
        max_age=8 * 60 * 60,
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
        "WHERE devices.archived_at IS NULL "
        "ORDER BY (assignments.id IS NOT NULL), devices.device_id COLLATE NOCASE",
        (user["id"],),
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
        "summary": {
            "patients": len(patient_items),
            "devices_total": len(device_items),
            "devices_available": sum(1 for item in device_items if item["available"]),
            "devices_assigned": sum(1 for item in device_items if not item["available"]),
        },
    }


@app.get("/api/v1/grafana/home")
def grafana_home_data(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    return medical_portal_data(verified_grafana_user(smartback_grafana_session))


@app.post("/api/v1/grafana/patients", status_code=201)
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
        raise HTTPException(status_code=404, detail="Nessun paziente registrato con questo codice fiscale")
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


@app.delete("/api/v1/grafana/patients/{patient_code}", status_code=204)
def grafana_remove_patient(
    patient_code: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, patient_code)
    assignments = auth_db.execute(
        "SELECT id,device_id FROM device_assignments "
        "WHERE patient_id=? AND released_at IS NULL",
        (patient["id"],),
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        auth_db.execute(
            "UPDATE device_assignments SET released_at=?,released_by=? "
            "WHERE patient_id=? AND released_at IS NULL",
            (now, user["id"], patient["id"]),
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


@app.post("/api/v1/grafana/devices", status_code=201)
def grafana_create_device(
    body: DeviceCreateRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    verified_grafana_user(smartback_grafana_session)
    now = datetime.now(timezone.utc).isoformat()
    try:
        auth_db.execute(
            "INSERT INTO devices(device_id,display_name,source_type,first_seen_at,last_seen_at,quality,has_telemetry) "
            "VALUES (?,?,?,?,?,?,0)",
            (
                body.device_id,
                body.display_name,
                "simulated",
                now,
                now,
                "simulated",
            ),
        )
        auth_db.commit()
    except sqlite3.IntegrityError:
        auth_db.rollback()
        raise HTTPException(status_code=409, detail="Identificativo maglia già presente") from None
    if mqtt_handler:
        mqtt_handler.publish_simulated_device(body.device_id, active=True)
    return {
        "device_id": body.device_id,
        "display_name": body.display_name,
        "has_telemetry": False,
    }


@app.delete("/api/v1/grafana/devices/{device_id}", status_code=204)
def grafana_remove_device(
    device_id: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    device = auth_db.execute(
        "SELECT devices.source_type,assignments.patient_id,links.doctor_id "
        "FROM devices LEFT JOIN device_assignments assignments "
        "ON assignments.device_id=devices.device_id AND assignments.released_at IS NULL "
        "LEFT JOIN doctor_patients links ON links.patient_id=assignments.patient_id "
        "AND links.doctor_id=? WHERE devices.device_id=? AND devices.archived_at IS NULL",
        (user["id"], device_id),
    ).fetchone()
    if device is None:
        raise HTTPException(status_code=404, detail="Maglia non trovata")
    if device["patient_id"] is not None and device["doctor_id"] is None:
        raise HTTPException(status_code=403, detail="Maglia assegnata a un altro medico")
    now = datetime.now(timezone.utc).isoformat()
    with database_lock:
        auth_db.execute(
            "UPDATE device_assignments SET released_at=?,released_by=? "
            "WHERE device_id=? AND released_at IS NULL",
            (now, user["id"], device_id),
        )
        auth_db.execute(
            "UPDATE devices SET archived_at=? WHERE device_id=?",
            (now, device_id),
        )
        auth_db.commit()
    if mqtt_handler:
        mqtt_handler.publish_device_assignment(device_id, None)
        if device["source_type"] == "simulated":
            mqtt_handler.publish_simulated_device(device_id, active=False)
    return Response(status_code=204)


@app.put("/api/v1/grafana/devices/{device_id}/assignment")
def grafana_assign_device(
    device_id: str,
    body: DeviceAssignmentRequest,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    patient = accessible_patient_by_code(user, body.patient_code)
    if auth_db.execute("SELECT 1 FROM devices WHERE device_id=?", (device_id,)).fetchone() is None:
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


@app.delete("/api/v1/grafana/devices/{device_id}/assignment", status_code=204)
def grafana_release_device(
    device_id: str,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    user = verified_grafana_user(smartback_grafana_session)
    assignment = auth_db.execute(
        "SELECT assignments.id FROM device_assignments assignments "
        "JOIN doctor_patients links ON links.patient_id=assignments.patient_id "
        "WHERE assignments.device_id=? AND assignments.released_at IS NULL "
        "AND links.doctor_id=?",
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


@app.get("/smartback/", response_class=HTMLResponse)
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
    header{{display:flex;justify-content:space-between;align-items:center;padding:22px 5vw;border-bottom:1px solid var(--line)}}
    main{{max-width:1200px;margin:auto;padding:34px 5vw 60px}} h1{{margin:0;font-size:25px}} h2{{font-size:20px;margin:34px 0 15px}}
    .muted{{color:var(--muted)}} .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
    .stat,.card,.device{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}}
    .stat b{{display:block;font-size:28px;margin-top:5px}} .toolbar{{display:flex;justify-content:space-between;align-items:center;gap:15px}}
    button,.button{{border:0;border-radius:9px;padding:11px 16px;background:var(--blue);color:white;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}}
    .secondary{{background:#273248}} .danger{{background:#54252b}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:14px}}
    .device-grid{{grid-template-columns:repeat(3,minmax(0,1fr));justify-content:start}}
    .card h3,.device h3{{margin:0 0 4px;font-size:18px}} .actions{{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}}
    .badge{{display:inline-block;padding:4px 9px;border-radius:99px;background:#263247;color:#cbd5e1;font-size:12px;font-weight:700}}
    .available{{background:#173b29;color:#8ce99a}} .assigned{{background:#412b16;color:#ffc078}}
    select,input{{width:100%;background:#0f1520;color:white;border:1px solid var(--line);border-radius:8px;padding:10px}}
    dialog{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:14px;max-width:460px;width:calc(100% - 30px);padding:24px}} dialog::backdrop{{background:#000a}}
    @media(max-width:900px){{.device-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @media(max-width:720px){{.stats{{grid-template-columns:repeat(2,1fr)}}.device-grid{{grid-template-columns:1fr}}header{{align-items:flex-start;gap:15px}}}}
    </style></head><body><header><div><h1>SmartBack</h1><div class="muted">Portale medico</div></div>
    <div><span class="muted">{doctor_name}</span> · <a href="/grafana-logout" style="color:#8ab4ff">Esci</a></div></header>
    <main><section class="stats" id="stats"></section>
    <section><div class="toolbar"><div><h2>I miei pazienti</h2><div class="muted">Seleziona la scheda clinica da consultare.</div></div>
    <button onclick="patientDialog.showModal()">＋ Aggiungi paziente</button></div><div class="grid" id="patients"></div></section>
    <section><div class="toolbar"><div><h2>Lista magliette</h2><div class="muted">Inventario e assegnazioni attive.</div></div>
    <button onclick="deviceDialog.showModal()">＋ Aggiungi maglia</button></div><div class="grid device-grid" id="devices"></div></section></main>
    <dialog id="patientDialog"><h2 style="margin-top:0">Associa un paziente</h2><p class="muted">Il paziente deve avere già creato il proprio account SmartBack.</p>
    <form id="patientForm"><label>Codice fiscale<input id="fiscalCode" maxlength="16" required style="margin-top:6px;text-transform:uppercase"></label>
    <p id="patientError" style="color:#ff8787;min-height:22px"></p><div class="actions"><button type="submit">Associa</button><button type="button" class="secondary" onclick="patientDialog.close()">Annulla</button></div></form></dialog>
    <dialog id="deviceDialog"><h2 style="margin-top:0">Aggiungi una maglia</h2>
    <form id="deviceForm" style="display:grid;gap:14px"><label>Nome visualizzato<input id="deviceName" placeholder="Maglia 3" required></label>
    <label>Codice maglia<input id="deviceId" placeholder="tshirt003" required></label>
    <p id="deviceError" style="color:#ff8787;min-height:22px;margin:0"></p><div class="actions"><button type="submit">Aggiungi</button><button type="button" class="secondary" onclick="deviceDialog.close()">Annulla</button></div></form></dialog>
    <script>
    const esc=s=>String(s??"").replace(/[&<>\"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;","'":"&#39;"}}[c]));
    let state={{patients:[],devices:[],summary:{{}}}};
    async function request(url,options={{}}){{const r=await fetch(url,{{...options,headers:{{"Content-Type":"application/json",...(options.headers||{{}})}}}});if(r.status===401)location.href="/grafana-login";if(!r.ok){{const b=await r.json().catch(()=>({{}}));throw Error(b.detail||"Operazione non riuscita")}}return r.status===204?null:r.json()}}
    async function load(){{state=await request("/api/v1/grafana/home");render()}}
    function render(){{const s=state.summary;stats.innerHTML=[["Pazienti",s.patients],["Magliette totali",s.devices_total],["Disponibili",s.devices_available],["Assegnate",s.devices_assigned]].map(x=>`<div class="stat"><span class="muted">${{x[0]}}</span><b>${{x[1]}}</b></div>`).join("");
    patients.innerHTML=state.patients.length?state.patients.map(p=>{{const code=encodeURIComponent(p.patient_code);const free=state.devices.filter(d=>d.available);return `<article class="card"><h3>${{esc(p.name)}}</h3><div class="muted">${{esc(p.patient_code)}}</div><p>${{p.assigned_device?`<span class="badge assigned">Maglia ${{esc(p.assigned_device)}}</span>`:'<span class="badge">Nessuna maglia</span>'}}</p><div class="actions"><a class="button" href="/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id=${{code}}&refresh=1s">Monitoraggio live</a><a class="button" href="/grafana/d/smartback-history/smartback-storico-paziente?var-patient_id=${{code}}">Storico</a></div>${{!p.assigned_device&&free.length?`<div class="actions"><select id="shirt-${{esc(p.id)}}">${{free.map(d=>`<option value="${{esc(d.device_id)}}">${{esc(d.display_name)}}</option>`).join('')}}</select><button onclick="assign('${{esc(p.id)}}','${{esc(p.patient_code)}}')">Assegna maglia</button></div>`:''}}<div class="actions"><button class="danger" onclick="removePatient('${{esc(p.patient_code)}}','${{esc(p.name)}}')">Rimuovi paziente</button></div></article>`}}).join(""):'<div class="card muted">Nessun paziente associato. Usa “Aggiungi paziente” per iniziare.</div>';
    devices.innerHTML=state.devices.length?state.devices.map(d=>`<article class="device"><h3>${{esc(d.display_name)}}</h3><div class="muted">${{esc(d.device_id)}}</div><p><span class="badge ${{d.has_telemetry?'available':''}}">${{d.has_telemetry?'Connessa':'Non connessa'}}</span> <span class="badge ${{d.available?'available':'assigned'}}">${{d.available?'Disponibile':'Assegnata'}}</span></p>${{d.patient_name?`<div>Assegnata a: <b>${{esc(d.patient_name)}}</b></div>`:''}}<div class="actions">${{!d.available&&d.patient_name!=='Altro paziente'?`<button class="danger" onclick="releaseShirt('${{esc(d.device_id)}}')">Libera maglia</button>`:''}}<button class="danger" onclick="removeDevice('${{esc(d.device_id)}}','${{esc(d.display_name)}}')">Rimuovi maglia</button></div></article>`).join(""):'<div class="device muted">Nessuna maglia registrata.</div>'}}
    async function assign(patientId,patientCode){{const device=document.getElementById('shirt-'+patientId).value;await request('/api/v1/grafana/devices/'+encodeURIComponent(device)+'/assignment',{{method:'PUT',body:JSON.stringify({{patient_code:patientCode}})}});await load()}}
    async function releaseShirt(device){{if(!confirm('Liberare questa maglia? Lo storico precedente resterà associato al paziente.'))return;await request('/api/v1/grafana/devices/'+encodeURIComponent(device)+'/assignment',{{method:'DELETE'}});await load()}}
    async function removePatient(code,name){{if(!confirm(`Rimuovere ${{name}} dalla lista dei pazienti? La maglia verrà liberata, ma account e storico resteranno conservati.`))return;await request('/api/v1/grafana/patients/'+encodeURIComponent(code),{{method:'DELETE'}});await load()}}
    async function removeDevice(device,name){{if(!confirm(`Rimuovere ${{name}} dall'inventario? Le assegnazioni e lo storico resteranno conservati.`))return;await request('/api/v1/grafana/devices/'+encodeURIComponent(device),{{method:'DELETE'}});await load()}}
    patientForm.addEventListener('submit',async e=>{{e.preventDefault();patientError.textContent='';try{{await request('/api/v1/grafana/patients',{{method:'POST',body:JSON.stringify({{fiscal_code:fiscalCode.value}})}});patientDialog.close();patientForm.reset();await load()}}catch(err){{patientError.textContent=err.message}}}});load().catch(e=>document.querySelector('main').innerHTML='<p>'+esc(e.message)+'</p>');
    deviceForm.addEventListener('submit',async e=>{{e.preventDefault();deviceError.textContent='';try{{await request('/api/v1/grafana/devices',{{method:'POST',body:JSON.stringify({{device_id:deviceId.value,display_name:deviceName.value}})}});deviceDialog.close();deviceForm.reset();await load()}}catch(err){{deviceError.textContent=err.message}}}});
    </script></body></html>
    """


@app.get("/api/v1/grafana/auth")
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


@app.post("/api/v1/grafana/token-rotation")
def grafana_token_rotation(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    # Con auth proxy non esiste un token Grafana da ruotare. Il frontend
    # richiede comunque questo endpoint e, su 401, ricarica l'intera pagina.
    verified_grafana_user(smartback_grafana_session)
    return {"status": "ok"}


@app.post("/api/v1/grafana/patients/{patient_code}/calibration")
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


@app.post(
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


@app.post(
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


@app.get("/grafana-calibration", response_class=HTMLResponse)
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
          result.style.color = "#344054";
          result.textContent = "Calibrazione in corso…";
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
          result.style.color = "#067647";
          result.textContent = `Calibrazione salvata: pitch ${{body.reference_pitch_deg}}° · roll ${{body.reference_roll_deg}}°`;
          setTimeout(() => {{
            window.location.href = "/grafana/d/smartback-overview/smartback-monitoraggio-paziente?var-patient_id={safe_patient}&refresh=1s";
          }}, 900);
        }});
      </script>
    </main>
    """


@app.post("/api/v1/grafana/logout", status_code=204)
def grafana_logout(
    response: Response,
    smartback_grafana_session: str | None = Cookie(default=None),
):
    if smartback_grafana_session:
        auth_db.execute("DELETE FROM sessions WHERE token=?", (smartback_grafana_session,))
        auth_db.commit()
    response.delete_cookie(GRAFANA_SESSION_COOKIE, path="/")


@app.get("/grafana-logout")
def grafana_browser_logout(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    if smartback_grafana_session:
        auth_db.execute("DELETE FROM sessions WHERE token=?", (smartback_grafana_session,))
        auth_db.commit()
    response = RedirectResponse(url="/grafana-login", status_code=303)
    response.delete_cookie(GRAFANA_SESSION_COOKIE, path="/")
    return response


@app.get("/api/v1/auth/me")
def me(user: sqlite3.Row = Depends(current_user)):
    return public_user(user)


@app.post("/api/v1/auth/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        auth_db.execute("DELETE FROM sessions WHERE token=?", (authorization.removeprefix("Bearer ").strip(),))
        auth_db.commit()


@app.put("/api/v1/auth/password", status_code=204)
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


@app.put("/api/v1/auth/avatar")
def change_avatar(body: AvatarRequest, user: sqlite3.Row = Depends(current_user)):
    auth_db.execute("UPDATE users SET avatar_data=? WHERE id=?", (body.avatar_data, user["id"]))
    auth_db.commit()
    updated_user = auth_db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    return public_user(updated_user)


@app.get("/api/v1/doctor/patients")
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


@app.post("/api/v1/doctor/patients", status_code=201)
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


@app.get("/health")
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


@app.get("/api/v1/posture/latest")
def get_latest_posture():
    latest = mqtt_handler.latest_posture if mqtt_handler else None
    if latest is None:
        raise HTTPException(status_code=404, detail="Nessun campione posturale ancora ricevuto")
    return latest


@app.get("/api/v1/device/latest")
def get_latest_device():
    latest = mqtt_handler.latest_device if mqtt_handler else None
    if latest is None:
        raise HTTPException(status_code=404, detail="Nessuno stato del dispositivo ancora ricevuto")
    return latest


@app.post("/api/v1/devices/{device_id}/calibration")
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


@app.get("/api/v1/posture/history")
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


@app.get("/api/v1/posture/history/availability")
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


@app.get("/api/v1/patient/statistics")
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


@app.get("/api/v1/doctor/patients/{patient_id}/monitoring-config")
def get_monitoring_config(patient_id: str, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    patient = accessible_patient(user, patient_id)
    return monitoring_config_for_patient(patient)


@app.put("/api/v1/doctor/patients/{patient_id}/monitoring-config")
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


@app.delete("/api/v1/doctor/patients/{patient_id}/monitoring-config")
def reset_monitoring_config(patient_id: str, user: sqlite3.Row = Depends(current_user)):
    if user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    patient = accessible_patient(user, patient_id)
    auth_db.execute("DELETE FROM monitoring_configs WHERE patient_id=?", (patient["id"],))
    auth_db.commit()
    return monitoring_config_for_patient(patient)


@app.websocket("/ws/wearable")
async def wearable_stream(websocket: WebSocket):
    await websocket.accept()
    websockets.add(websocket)
    try:
        latest = mqtt_handler.latest_posture if mqtt_handler else None
        if latest:
            await websocket.send_json(latest)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websockets.discard(websocket)
