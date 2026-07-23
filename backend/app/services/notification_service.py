import asyncio
import secrets
from typing import Any, Callable

from app.repositories.notification_repository import NotificationRepository


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        mapper: Callable[[dict[str, Any]], dict[str, Any] | None],
        sender: Callable[[list[str], dict[str, Any]], int],
        cooldown_seconds: float,
        delivery_lock: asyncio.Lock,
        last_processed: dict[tuple[str, str], float],
    ):
        self.repository = repository
        self.mapper = mapper
        self.sender = sender
        self.cooldown_seconds = cooldown_seconds
        self.delivery_lock = delivery_lock
        self.last_processed = last_processed

    async def send_test(self, user_id: str) -> tuple[int, int]:
        """Invia la notifica diagnostica senza esporre il repository all'API."""
        tokens = self.repository.tokens(user_id)
        if not tokens:
            return 0, 0
        notification = {
            "title": "Notifica SmartBack",
            "body": "Le notifiche sul dispositivo funzionano correttamente.",
            "channelId": "smartshirt_alerts_v2",
            "sound": "default",
            "priority": "high",
            "data": {"code": "PUSH_TEST"},
        }
        accepted = await asyncio.to_thread(self.sender, tokens, notification)
        return len(tokens), accepted

    async def dispatch(self, alert: dict[str, Any]) -> int:
        notification = self.mapper(alert)
        if notification is None:
            return 0
        user_id, tokens = self.repository.recipient(
            str(alert.get("patient_id") or "")
        )
        if user_id is None or not tokens:
            return 0
        code = str(alert.get("code") or "UNKNOWN")
        key = (user_id, code)
        async with self.delivery_lock:
            now = asyncio.get_running_loop().time()
            previous = self.last_processed.get(key)
            if previous is not None and now - previous < self.cooldown_seconds:
                return 0
            self.last_processed[key] = now
            self.repository.add(
                f"ntf_{secrets.token_hex(10)}", user_id,
                notification["title"], notification["body"], code,
            )
            return await asyncio.to_thread(self.sender, tokens, notification)
