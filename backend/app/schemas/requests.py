"""Schemi di ingresso delle API.

Questo modulo valida forma e vincoli dei dati HTTP. Non accede a database,
MQTT o servizi applicativi.
"""

import base64
import binascii
import hmac
import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.config import MEDICAL_REGISTRATION_CODE
from app.domain.fiscal_code import is_valid_fiscal_code


EMAIL_DOMAIN_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$",
    re.IGNORECASE,
)


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
        if not re.fullmatch(
            r"[^\W\d_]+(?:[ '\u2019-][^\W\d_]+)*",
            normalized,
            re.UNICODE,
        ):
            raise ValueError(
                "Nome e cognome possono contenere solo lettere, spazi e apostrofi"
            )
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
        if not re.search(r"\d", value) or not re.search(
            r"[^\w\s]", value, re.UNICODE
        ):
            raise ValueError(
                "La password deve contenere almeno un numero e un simbolo speciale"
            )
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
            if not self.medical_code or not hmac.compare_digest(
                self.medical_code.strip(), MEDICAL_REGISTRATION_CODE
            ):
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
        if not re.search(r"\d", value) or not re.search(
            r"[^\w\s]", value, re.UNICODE
        ):
            raise ValueError(
                "La nuova password deve contenere almeno un numero e un simbolo speciale"
            )
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
        prefix = next(
            (candidate for candidate in prefixes if value.startswith(candidate)),
            None,
        )
        if prefix is None:
            raise ValueError("La foto deve essere in formato JPEG o PNG")
        try:
            decoded = base64.b64decode(value[len(prefix):], validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("La foto selezionata non è valida") from None
        if len(decoded) > 2_000_000:
            raise ValueError(
                "La foto è troppo grande; scegli un'immagine inferiore a 2 MB"
            )
        return value


class PushTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)

    @field_validator("token")
    @classmethod
    def validate_expo_token(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(
            r"(?:Exponent|Expo)PushToken\[[A-Za-z0-9_-]+\]",
            normalized,
        ):
            raise ValueError("Token Expo Push non valido")
        return normalized


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
            raise ValueError(
                "La soglia pitch marcata deve essere maggiore "
                "della soglia pitch moderata"
            )
        if self.marked_roll_deg <= self.moderate_roll_deg:
            raise ValueError(
                "La soglia roll marcata deve essere maggiore "
                "della soglia roll moderata"
            )
        return self
