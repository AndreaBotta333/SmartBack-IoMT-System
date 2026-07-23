"""Casi d'uso di autenticazione, registrazione e gestione dell'account."""

import hmac
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from app.repositories.identity_repository import IdentityRepository


class InvalidCredentials(Exception): pass
class EmailAlreadyRegistered(Exception): pass
class FiscalCodeAlreadyRegistered(Exception): pass
class IdentityConflict(Exception): pass
class InvalidCurrentPassword(Exception): pass
class ProtectedAccount(Exception): pass
class AccountDeactivationFailed(Exception): pass


class AuthService:
    def __init__(
        self,
        repository: IdentityRepository,
        password_hasher: Callable[..., tuple[str, str]],
    ):
        self.repository = repository
        self.password_hasher = password_hasher

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.repository.create_session(user_id, token)
        return token

    def user_for_session(self, token: str) -> sqlite3.Row | None:
        return self.repository.user_for_session(token)

    def logout(self, token: str) -> None:
        self.repository.delete_session(token)

    def ensure_grafana_admin(self, password: str) -> None:
        digest, salt = self.password_hasher(password)
        self.repository.ensure_grafana_admin(
            email="admin@smartback.local",
            password_digest=digest,
            password_salt=salt,
        )

    def authenticate(self, email: str, password: str) -> sqlite3.Row:
        user = self.repository.user_by_email(email.lower().strip())
        if user is None or not bool(user["account_registered"]):
            raise InvalidCredentials
        digest, _ = self.password_hasher(
            password, bytes.fromhex(user["password_salt"])
        )
        if not hmac.compare_digest(digest, user["password_hash"]):
            raise InvalidCredentials
        return user

    def register(
        self, *, role: str, email: str, password: str, first_name: str,
        last_name: str, fiscal_code: str | None,
    ) -> sqlite3.Row:
        email = email.lower().strip()
        if self.repository.user_by_email(email):
            raise EmailAlreadyRegistered
        digest, salt = self.password_hasher(password)
        full_name = f"{first_name} {last_name}"
        pending = (
            self.repository.patient_by_fiscal_code(str(fiscal_code))
            if role == "patient" else None
        )
        if pending is not None and bool(pending["account_registered"]):
            raise FiscalCodeAlreadyRegistered
        try:
            if pending is not None:
                return self.repository.claim_pending_patient(
                    str(pending["id"]), full_name, first_name, last_name,
                    email, digest, salt,
                )
            user_id = f"usr_{secrets.token_hex(8)}"
            patient_code = (
                f"patient-{user_id.removeprefix('usr_')}"
                if role == "patient" else None
            )
            return self.repository.insert_user(
                (
                    user_id, full_name, first_name, last_name, email, digest,
                    salt, role, datetime.now(timezone.utc).isoformat(),
                    patient_code, fiscal_code, 1 if role == "doctor" else 0,
                )
            )
        except sqlite3.IntegrityError as error:
            self.repository.database.rollback()
            raise IdentityConflict from error

    def deactivate_account(self, user: sqlite3.Row) -> None:
        user_id = str(user["id"])
        if user_id == "usr_grafana_admin":
            raise ProtectedAccount
        tombstone_email = f"deleted-{user_id}@smartback.invalid"
        digest, salt = self.password_hasher(secrets.token_urlsafe(48))
        try:
            self.repository.deactivate_account(
                user_id, tombstone_email, digest, salt
            )
        except sqlite3.Error as error:
            raise AccountDeactivationFailed from error

    def change_password(
        self,
        user: sqlite3.Row,
        current_password: str,
        new_password: str,
    ) -> None:
        current_digest, _ = self.password_hasher(
            current_password,
            bytes.fromhex(user["password_salt"]),
        )
        if not hmac.compare_digest(current_digest, user["password_hash"]):
            raise InvalidCurrentPassword
        digest, salt = self.password_hasher(new_password)
        self.repository.update_password(str(user["id"]), digest, salt)

    def change_avatar(
        self, user_id: str, avatar_data: str | None
    ) -> sqlite3.Row:
        return self.repository.update_avatar(user_id, avatar_data)
