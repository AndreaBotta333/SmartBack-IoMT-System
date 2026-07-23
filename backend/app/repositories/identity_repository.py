import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IdentityRepository:
    def __init__(self, database: sqlite3.Connection, fallback_path: str):
        self.database = database
        self.fallback_path = fallback_path

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()

    def user_by_id(self, user_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()

    def ensure_grafana_admin(
        self,
        *,
        email: str,
        password_digest: str,
        password_salt: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.database.execute(
            "INSERT INTO users("
            "id,name,first_name,last_name,email,password_hash,password_salt,"
            "role,created_at,patient_code,fiscal_code,professional_verified"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET email=excluded.email,"
            "password_hash=excluded.password_hash,"
            "password_salt=excluded.password_salt,professional_verified=1",
            (
                "usr_grafana_admin",
                "Amministratore SmartBack",
                "Amministratore",
                "SmartBack",
                email,
                password_digest,
                password_salt,
                "doctor",
                now,
                None,
                None,
                1,
            ),
        )
        self.database.commit()

    def patient_by_fiscal_code(self, fiscal_code: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE fiscal_code=? AND role='patient'",
            (fiscal_code,),
        ).fetchone()

    def insert_user(self, values: tuple[Any, ...]) -> sqlite3.Row:
        self.database.execute(
            "INSERT INTO users(id,name,first_name,last_name,email,password_hash,"
            "password_salt,role,created_at,patient_code,fiscal_code,"
            "professional_verified,account_registered) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
            values,
        )
        self.database.commit()
        user = self.user_by_id(str(values[0]))
        if user is None:
            raise RuntimeError("Utente appena creato non trovato")
        return user

    def claim_pending_patient(
        self,
        user_id: str,
        name: str,
        first_name: str,
        last_name: str,
        email: str,
        digest: str,
        salt: str,
    ) -> sqlite3.Row:
        self.database.execute(
            "UPDATE users SET name=?,first_name=?,last_name=?,email=?,"
            "password_hash=?,password_salt=?,account_registered=1 WHERE id=?",
            (name, first_name, last_name, email, digest, salt, user_id),
        )
        self.database.commit()
        user = self.user_by_id(user_id)
        if user is None:
            raise RuntimeError("Utente registrato non trovato")
        return user

    def create_session(self, user_id: str, token: str) -> None:
        self.database.execute(
            "INSERT INTO sessions(token,user_id,created_at) VALUES (?,?,?)",
            (token, user_id, datetime.now(timezone.utc).isoformat()),
        )
        self.database.commit()

    def user_for_session(self, token: str) -> sqlite3.Row | None:
        database = self.database.execute("PRAGMA database_list").fetchone()
        database_path = str(database["file"] or self.fallback_path)
        with sqlite3.connect(Path(database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                "SELECT users.* FROM sessions JOIN users "
                "ON users.id=sessions.user_id WHERE sessions.token=?",
                (token,),
            ).fetchone()

    def delete_session(self, token: str) -> None:
        self.database.execute("DELETE FROM sessions WHERE token=?", (token,))
        self.database.commit()

    def deactivate_account(
        self,
        user_id: str,
        tombstone_email: str,
        password_digest: str,
        password_salt: str,
    ) -> None:
        """Revoca l'accesso mantenendo il profilo clinico indipendente."""
        try:
            self.database.execute(
                "DELETE FROM push_tokens WHERE user_id=?", (user_id,)
            )
            self.database.execute(
                "DELETE FROM app_notifications WHERE user_id=?", (user_id,)
            )
            self.database.execute(
                "DELETE FROM sessions WHERE user_id=?", (user_id,)
            )
            self.database.execute(
                "UPDATE users SET email=?,password_hash=?,password_salt=?,"
                "avatar_data=NULL,account_registered=0 WHERE id=?",
                (
                    tombstone_email,
                    password_digest,
                    password_salt,
                    user_id,
                ),
            )
            self.database.commit()
        except sqlite3.Error:
            self.database.rollback()
            raise

    def update_password(
        self, user_id: str, password_digest: str, password_salt: str
    ) -> None:
        self.database.execute(
            "UPDATE users SET password_hash=?,password_salt=? WHERE id=?",
            (password_digest, password_salt, user_id),
        )
        self.database.commit()

    def update_avatar(
        self, user_id: str, avatar_data: str | None
    ) -> sqlite3.Row:
        self.database.execute(
            "UPDATE users SET avatar_data=? WHERE id=?",
            (avatar_data, user_id),
        )
        self.database.commit()
        user = self.user_by_id(user_id)
        if user is None:
            raise RuntimeError("Utente aggiornato non trovato")
        return user

    def associated_patient_by_id(
        self, doctor_id: str, patient_id: str
    ) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT patients.* FROM doctor_patients links "
            "JOIN users patients ON patients.id=links.patient_id "
            "WHERE links.doctor_id=? AND patients.id=?",
            (doctor_id, patient_id),
        ).fetchone()

    def associated_patient_by_code(
        self, doctor_id: str, patient_code: str
    ) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT patients.* FROM doctor_patients links "
            "JOIN users patients ON patients.id=links.patient_id "
            "WHERE links.doctor_id=? AND patients.patient_code=?",
            (doctor_id, patient_code),
        ).fetchone()

    def patient_by_code(self, patient_code: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM users WHERE role='patient' AND patient_code=?",
            (patient_code,),
        ).fetchone()
