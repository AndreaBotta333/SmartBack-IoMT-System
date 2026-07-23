import sqlite3
import threading
from datetime import datetime, timezone


class NotificationRepository:
    def __init__(self, database: sqlite3.Connection, lock: threading.RLock):
        self.database = database
        self.lock = lock

    def recipient(self, patient_code: str) -> tuple[str | None, list[str]]:
        with self.lock:
            user = self.database.execute(
                "SELECT id FROM users WHERE patient_code=? "
                "AND account_registered=1",
                (patient_code,),
            ).fetchone()
            if user is None:
                return None, []
            rows = self.database.execute(
                "SELECT token FROM push_tokens WHERE user_id=?", (user["id"],)
            ).fetchall()
        return str(user["id"]), [str(row["token"]) for row in rows]

    def tokens(self, user_id: str) -> list[str]:
        rows = self.database.execute(
            "SELECT token FROM push_tokens WHERE user_id=?", (user_id,)
        ).fetchall()
        return [str(row["token"]) for row in rows]

    def register_token(self, user_id: str, token: str) -> None:
        self.database.execute(
            "INSERT INTO push_tokens(token,user_id,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id,"
            "updated_at=excluded.updated_at",
            (token, user_id, datetime.now(timezone.utc).isoformat()),
        )
        self.database.commit()

    def unregister_token(self, user_id: str, token: str) -> None:
        self.database.execute(
            "DELETE FROM push_tokens WHERE token=? AND user_id=?", (token, user_id)
        )
        self.database.commit()

    def add(self, notification_id: str, user_id: str, title: str, body: str, code: str) -> None:
        with self.lock:
            self.database.execute(
                "INSERT INTO app_notifications("
                "id,user_id,title,body,code,created_at) VALUES (?,?,?,?,?,?)",
                (
                    notification_id, user_id, title, body, code,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.database.commit()

    def list(self, user_id: str, limit: int) -> list[dict]:
        rows = self.database.execute(
            "SELECT id,title,body,code,created_at FROM app_notifications "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, max(1, min(limit, 250))),
        ).fetchall()
        return [dict(row) for row in rows]

    def clear(self, user_id: str) -> None:
        self.database.execute(
            "DELETE FROM app_notifications WHERE user_id=?", (user_id,)
        )
        self.database.commit()
