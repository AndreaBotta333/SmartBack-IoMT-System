import asyncio
import base64
import binascii
import hashlib
import hmac
import math
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import (
    ALERT_TOPIC, AUTH_DB_PATH, DATA_STALE_SECONDS, DEVICE_TOPIC, INFLUX_BUCKET,
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

websockets: set[WebSocket] = set()
influx_manager: InfluxManager | None = None
posture_engine: PostureEngine | None = None
mqtt_handler: SmartBackMqttHandler | None = None
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
    return auth_db.execute(
        "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=?",
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


async def broadcast(payload: dict[str, Any]) -> None:
    stale = []
    for socket in list(websockets):
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        websockets.discard(socket)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_handler, influx_manager, posture_engine, auth_db
    loop = asyncio.get_running_loop()
    auth_db = init_database(AUTH_DB_PATH)
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
    <main style="max-width:420px;margin:8vh auto;padding:24px;font-family:system-ui,sans-serif">
      <h1 style="font-size:24px">SmartBack · Accesso medico</h1>
      <p>Accedi con le credenziali SmartBack verificate per il ruolo medico.</p>
      <form id="login" style="display:grid;gap:14px">
        <label>Email <input id="email" type="email" required
          style="display:block;width:100%;box-sizing:border-box;padding:10px;margin-top:5px"></label>
        <label>Password <input id="password" type="password" required
          style="display:block;width:100%;box-sizing:border-box;padding:10px;margin-top:5px"></label>
        <button type="submit" style="padding:11px;cursor:pointer">Accedi alla dashboard</button>
        <p id="error" role="alert" style="color:#b42318;min-height:1.4em"></p>
      </form>
      <script>
        document.getElementById("login").addEventListener("submit", async (event) => {
          event.preventDefault();
          const error = document.getElementById("error");
          error.textContent = "";
          const response = await fetch("/api/v1/grafana/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              email: document.getElementById("email").value,
              password: document.getElementById("password").value
            })
          });
          if (response.ok) {
            window.location.assign("/grafana/");
            return;
          }
          const body = await response.json().catch(() => ({}));
          error.textContent = body.detail || "Accesso non riuscito";
        });
      </script>
    </main>
    """


@app.post("/api/v1/grafana/login")
def grafana_login(body: LoginRequest, response: Response):
    user = authenticate_user(str(body.email), body.password)
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
    return {"status": "ok", "redirect": "/grafana/"}


@app.get("/api/v1/grafana/auth")
def grafana_auth(
    smartback_grafana_session: str | None = Cookie(default=None),
):
    if not smartback_grafana_session:
        raise HTTPException(status_code=401, detail="Sessione Grafana richiesta")
    user = user_for_session(smartback_grafana_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Sessione Grafana non valida")
    if user["role"] != "doctor" or not bool(user["professional_verified"]):
        raise HTTPException(status_code=403, detail="Accesso riservato ai medici verificati")
    return Response(
        status_code=200,
        headers={
            "X-WEBAUTH-USER": user["email"],
            "X-WEBAUTH-NAME": user["name"],
            "X-WEBAUTH-ROLE": "Viewer",
        },
    )


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
def calibrate(device_id: str):
    if mqtt_handler is None:
        raise HTTPException(status_code=503, detail="Motore posturale non disponibile")
    try:
        return mqtt_handler.calibrate(device_id)
    except LookupError:
        raise HTTPException(
            status_code=409,
            detail="Nessun campione corrente disponibile per questo dispositivo",
        ) from None


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
