import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
POSTURE_TOPIC = os.getenv("MQTT_POSTURE_TOPIC", "smartback/normalized/posture")
DEVICE_TOPIC = os.getenv("MQTT_DEVICE_TOPIC", "smartback/normalized/device")
INFLUX_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUXDB_ORG", "smartback")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "posture")

# Demonstration defaults, not clinical thresholds. They will become configurable.
MODERATE_DEVIATION_DEG = float(os.getenv("MODERATE_DEVIATION_DEG", "10"))
MARKED_DEVIATION_DEG = float(os.getenv("MARKED_DEVIATION_DEG", "20"))
PERSISTENCE_SECONDS = float(os.getenv("PERSISTENCE_SECONDS", "5"))
AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", "/app/data/smartback.db")
MEDICAL_REGISTRATION_CODE = os.getenv("MEDICAL_REGISTRATION_CODE", "SMARTBACK-MED-2026")
EMAIL_DOMAIN_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)

state_lock = threading.Lock()
latest_posture: dict[str, Any] | None = None
latest_device: dict[str, Any] | None = None
reference_pitch_by_device: dict[str, float] = {}
deviation_started_by_device: dict[str, float] = {}
websockets: set[WebSocket] = set()
main_loop: asyncio.AbstractEventLoop | None = None
mqtt_client: mqtt.Client | None = None
influx_client: InfluxDBClient | None = None
write_api = None
auth_db: sqlite3.Connection | None = None


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


class AssociatePatientRequest(BaseModel):
    fiscal_code: str = Field(min_length=16, max_length=16)

    @field_validator("fiscal_code")
    @classmethod
    def validate_fiscal_code(cls, value: str) -> str:
        normalized = value.upper().replace(" ", "")
        if not is_valid_fiscal_code(normalized):
            raise ValueError("Codice fiscale non valido")
        return normalized


class MonitoringConfigRequest(BaseModel):
    moderate_deviation_deg: float = Field(ge=1, le=45)
    marked_deviation_deg: float = Field(ge=2, le=60)
    persistence_seconds: float = Field(ge=1, le=300)

    @model_validator(mode="after")
    def validate_threshold_order(self):
        if self.marked_deviation_deg <= self.moderate_deviation_deg:
            raise ValueError("La soglia marcata deve essere maggiore della soglia moderata")
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


def init_auth_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    connection = sqlite3.connect(AUTH_DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, password_salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient', 'doctor')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS push_tokens (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS doctor_patients (
            doctor_id TEXT NOT NULL, patient_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doctor_id, patient_id),
            FOREIGN KEY(doctor_id) REFERENCES users(id),
            FOREIGN KEY(patient_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS monitoring_configs (
            patient_id TEXT PRIMARY KEY,
            moderate_deviation_deg REAL NOT NULL,
            marked_deviation_deg REAL NOT NULL,
            persistence_seconds REAL NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(updated_by) REFERENCES users(id)
        );
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
    if "patient_code" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN patient_code TEXT")
    for column, definition in (
        ("first_name", "TEXT"), ("last_name", "TEXT"),
        ("fiscal_code", "TEXT"), ("professional_verified", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in columns:
            connection.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    existing_users = connection.execute("SELECT id,name,first_name,last_name,role FROM users").fetchall()
    for existing in existing_users:
        if not existing["first_name"] or not existing["last_name"]:
            parts = existing["name"].strip().split(maxsplit=1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else "Utente"
            connection.execute(
                "UPDATE users SET first_name=?,last_name=?,professional_verified=? WHERE id=?",
                (first_name, last_name, 1 if existing["role"] == "doctor" else 0, existing["id"]),
            )
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_fiscal_code ON users(fiscal_code) WHERE fiscal_code IS NOT NULL")
    patients = connection.execute(
        "SELECT id, patient_code FROM users WHERE role='patient' ORDER BY created_at"
    ).fetchall()
    for index, patient in enumerate(patients):
        if not patient["patient_code"]:
            code = "patient-demo-001" if index == 0 else f"patient-{patient['id'].removeprefix('usr_')}"
            connection.execute("UPDATE users SET patient_code=? WHERE id=?", (code, patient["id"]))
    connection.commit()
    return connection


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
    }


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    auth_db.execute(
        "INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now(timezone.utc).isoformat()),
    )
    auth_db.commit()
    return token


def current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    token = authorization.removeprefix("Bearer ").strip()
    row = auth_db.execute(
        "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=?",
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    return row


def monitoring_config_for_patient(patient: sqlite3.Row) -> dict[str, float]:
    row = auth_db.execute(
        "SELECT moderate_deviation_deg,marked_deviation_deg,persistence_seconds FROM monitoring_configs WHERE patient_id=?",
        (patient["id"],),
    ).fetchone()
    return {
        "moderate_deviation_deg": float(row["moderate_deviation_deg"]) if row else MODERATE_DEVIATION_DEG,
        "marked_deviation_deg": float(row["marked_deviation_deg"]) if row else MARKED_DEVIATION_DEG,
        "persistence_seconds": float(row["persistence_seconds"]) if row else PERSISTENCE_SECONDS,
    }


def monitoring_config_for_patient_code(patient_code: str) -> dict[str, float]:
    patient = auth_db.execute(
        "SELECT * FROM users WHERE patient_code=? AND role='patient'", (patient_code,)
    ).fetchone()
    if patient is None:
        return {
            "moderate_deviation_deg": MODERATE_DEVIATION_DEG,
            "marked_deviation_deg": MARKED_DEVIATION_DEG,
            "persistence_seconds": PERSISTENCE_SECONDS,
        }
    return monitoring_config_for_patient(patient)


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


def vector_pitch(x: float, y: float, z: float) -> float:
    return math.degrees(math.atan2(y, math.sqrt(x * x + z * z)))


def vector_roll(x: float, y: float, z: float) -> float:
    return math.degrees(math.atan2(x, math.sqrt(y * y + z * z)))


def process_posture(payload: dict[str, Any]) -> dict[str, Any]:
    device_id = payload["device_id"]
    pitch = vector_pitch(float(payload["x"]), float(payload["y"]), float(payload["z"]))
    roll = vector_roll(float(payload["x"]), float(payload["y"]), float(payload["z"]))
    timestamp_ms = int(payload["timestamp"])
    config = monitoring_config_for_patient_code(str(payload["patient_id"]))
    moderate_deviation_deg = config["moderate_deviation_deg"]
    marked_deviation_deg = config["marked_deviation_deg"]
    persistence_seconds = config["persistence_seconds"]

    with state_lock:
        if device_id not in reference_pitch_by_device:
            reference_pitch_by_device[device_id] = pitch
        reference = reference_pitch_by_device[device_id]
        deviation = pitch - reference

        if abs(deviation) >= moderate_deviation_deg:
            deviation_started_by_device.setdefault(device_id, timestamp_ms / 1000)
        else:
            deviation_started_by_device.pop(device_id, None)
        started = deviation_started_by_device.get(device_id)
        duration = max(0.0, timestamp_ms / 1000 - started) if started else 0.0

    if abs(deviation) >= marked_deviation_deg and duration >= persistence_seconds:
        status, alert = "marked_deviation", "POSTURE_MARKED_DEVIATION"
    elif abs(deviation) >= moderate_deviation_deg and duration >= persistence_seconds:
        status, alert = "prolonged_deviation", "POSTURE_PROLONGED_DEVIATION"
    elif abs(deviation) >= moderate_deviation_deg:
        status, alert = "deviated", None
    else:
        status, alert = "neutral", None

    return {
        **payload,
        "pitch_deg": round(pitch, 2),
        "roll_deg": round(roll, 2),
        "reference_pitch_deg": round(reference, 2),
        "deviation_deg": round(deviation, 2),
        "deviation_duration_seconds": round(duration, 1),
        "posture_status": status,
        "alert": alert,
        "threshold_profile": f"patient:{payload['patient_id']}",
    }


def persist_posture(sample: dict[str, Any]) -> None:
    if write_api is None:
        return
    point = (
        Point("posture")
        .tag("device_id", sample["device_id"])
        .tag("patient_id", sample["patient_id"])
        .tag("status", sample["posture_status"])
        .field("pitch_deg", sample["pitch_deg"])
        .field("roll_deg", sample["roll_deg"])
        .field("deviation_deg", sample["deviation_deg"])
        .field("deviation_duration_seconds", sample["deviation_duration_seconds"])
        .field("alert_active", bool(sample["alert"]))
        .time(int(sample["timestamp"]), WritePrecision.MS)
    )
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


async def broadcast(payload: dict[str, Any]) -> None:
    stale = []
    for socket in list(websockets):
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        websockets.discard(socket)


def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
    if reason_code == 0:
        client.subscribe([(POSTURE_TOPIC, 1), (DEVICE_TOPIC, 1)])
        print(f"MQTT connected; subscribed to {POSTURE_TOPIC} and {DEVICE_TOPIC}", flush=True)
    else:
        print(f"MQTT connection failed: {reason_code}", flush=True)


def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    global latest_posture, latest_device
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        if message.topic == POSTURE_TOPIC:
            processed = process_posture(payload)
            persist_posture(processed)
            with state_lock:
                latest_posture = processed
            if main_loop:
                asyncio.run_coroutine_threadsafe(broadcast(processed), main_loop)
        elif message.topic == DEVICE_TOPIC:
            with state_lock:
                latest_device = payload
    except Exception as exc:
        print(f"Cannot process MQTT message from {message.topic}: {exc}", flush=True)


def start_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartback-backend")
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, mqtt_client, influx_client, write_api, auth_db
    main_loop = asyncio.get_running_loop()
    auth_db = init_auth_db()
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    mqtt_client = start_mqtt()
    yield
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    influx_client.close()
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
    user = auth_db.execute("SELECT * FROM users WHERE email=?", (body.email.lower().strip(),)).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Email o password non corrette")
    digest, _ = hash_password(body.password, bytes.fromhex(user["password_salt"]))
    if not hmac.compare_digest(digest, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o password non corrette")
    return {"access_token": create_session(user["id"]), "user": public_user(user)}


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
    return {**public_user(patient), "has_live_data": bool(latest_posture and patient["patient_code"] == latest_posture.get("patient_id"))}


@app.get("/health")
def health():
    mqtt_connected = bool(mqtt_client and mqtt_client.is_connected())
    influx_ready = False
    try:
        influx_ready = bool(influx_client and influx_client.health().status == "pass")
    except Exception:
        pass
    return {
        "status": "ok" if mqtt_connected and influx_ready else "degraded",
        "mqtt": mqtt_connected,
        "influxdb": influx_ready,
        "has_posture_data": latest_posture is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/posture/latest")
def get_latest_posture():
    with state_lock:
        if latest_posture is None:
            raise HTTPException(status_code=404, detail="Nessun campione posturale ancora ricevuto")
        return latest_posture


@app.get("/api/v1/device/latest")
def get_latest_device():
    with state_lock:
        if latest_device is None:
            raise HTTPException(status_code=404, detail="Nessuno stato del dispositivo ancora ricevuto")
        return latest_device


@app.post("/api/v1/devices/{device_id}/calibration")
def calibrate(device_id: str):
    with state_lock:
        if latest_posture is None or latest_posture.get("device_id") != device_id:
            raise HTTPException(status_code=409, detail="Nessun campione corrente disponibile per questo dispositivo")
        reference_pitch_by_device[device_id] = float(latest_posture["pitch_deg"])
        deviation_started_by_device.pop(device_id, None)
        return {"device_id": device_id, "reference_pitch_deg": reference_pitch_by_device[device_id]}


def query_posture_history(patient_code: str, minutes: int, limit: int = 600) -> list[dict[str, Any]]:
    minutes = min(max(minutes, 1), 10080)
    limit = min(max(limit, 1), 1200)
    window_seconds = max(1, math.ceil(minutes * 60 / 240))
    config = monitoring_config_for_patient_code(patient_code)
    query = f'''from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -{minutes}m)
      |> filter(fn: (r) => r._measurement == "posture")
      |> filter(fn: (r) => r._field == "deviation_deg")
      |> filter(fn: (r) => r.patient_id == "{patient_code}")
      |> group(columns: ["patient_id"])
      |> aggregateWindow(every: {window_seconds}s, fn: mean, createEmpty: false)
      |> sort(columns: ["_time"])
      |> limit(n: {limit})'''
    tables = influx_client.query_api().query(query=query, org=INFLUX_ORG)
    rows: list[dict[str, Any]] = []
    for table in tables:
        for record in table.records:
            deviation = round(float(record.get_value()), 2)
            if abs(deviation) >= config["marked_deviation_deg"]:
                status = "marked_deviation"
            elif abs(deviation) >= config["moderate_deviation_deg"]:
                status = "deviated"
            else:
                status = "neutral"
            rows.append({
                "timestamp": record.get_time().isoformat(),
                "deviation_deg": deviation,
                "posture_status": status,
                "is_incorrect": status != "neutral",
            })
    rows.sort(key=lambda item: item["timestamp"])
    return rows[-limit:]


@app.get("/api/v1/posture/history")
def posture_history(
    minutes: int = 60,
    patient_id: str | None = None,
    user: sqlite3.Row = Depends(current_user),
):
    patient = accessible_patient(user, patient_id)
    rows = query_posture_history(patient["patient_code"], minutes)
    return {"items": rows, "count": len(rows), "minutes": min(max(minutes, 1), 10080)}


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
        "INSERT INTO monitoring_configs(patient_id,moderate_deviation_deg,marked_deviation_deg,persistence_seconds,updated_at,updated_by) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(patient_id) DO UPDATE SET "
        "moderate_deviation_deg=excluded.moderate_deviation_deg,"
        "marked_deviation_deg=excluded.marked_deviation_deg,"
        "persistence_seconds=excluded.persistence_seconds,"
        "updated_at=excluded.updated_at,updated_by=excluded.updated_by",
        (patient["id"], body.moderate_deviation_deg, body.marked_deviation_deg, body.persistence_seconds,
         datetime.now(timezone.utc).isoformat(), user["id"]),
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
        if latest_posture:
            await websocket.send_json(latest_posture)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websockets.discard(websocket)
