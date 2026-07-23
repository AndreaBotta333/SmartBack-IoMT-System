"""Invio delle notifiche SmartBack tramite Expo Push Service."""

import json
import time
import urllib.error
import urllib.request
from typing import Any


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def notification_for_alert(alert: dict[str, Any]) -> dict[str, Any] | None:
    """Traduce gli alert rilevanti in notifiche italiane concise."""
    code = str(alert.get("code") or "")
    if not bool(alert.get("active", True)):
        return None
    content = {
        "POSTURE_PROLONGED_DEVIATION": (
            "Postura scorretta prolungata",
            "Fai una pausa e raddrizza la schiena.",
            "posture_alerts_v2",
        ),
        "POSTURE_MARKED_DEVIATION": (
            "Deviazione pronunciata",
            "È stata rilevata una deviazione posturale elevata.",
            "posture_alerts_v2",
        ),
        "BATTERY_LOW": (
            "Batteria della maglia scarica",
            "La batteria è al 20% o meno. Ricarica la smart t-shirt.",
            "smartshirt_alerts_v2",
        ),
        "BATTERY_CRITICAL": (
            "Batteria della maglia critica",
            "La batteria è al 10% o meno. Ricarica la smart t-shirt appena possibile.",
            "smartshirt_alerts_v2",
        ),
        "DATA_STREAM_STALE": (
            "Monitoraggio interrotto",
            "La smart t-shirt non sta più trasmettendo dati.",
            "smartshirt_alerts_v2",
        ),
    }.get(code)
    if content is None:
        return None
    title, body, channel_id = content
    return {
        "title": title,
        "body": body,
        "channelId": channel_id,
        "sound": "default",
        "priority": "high",
        "ttl": 3600,
        "data": {
            "code": code,
            "patient_id": str(alert.get("patient_id") or ""),
            "device_id": str(alert.get("device_id") or ""),
        },
    }


def send_expo_push(tokens: list[str], notification: dict[str, Any], attempts: int = 8) -> int:
    """Invia i messaggi ritentando gli errori temporanei DNS o di rete."""
    if not tokens:
        return 0
    messages = [{"to": token, **notification} for token in tokens]
    encoded_messages = json.dumps(messages).encode("utf-8")
    for attempt in range(1, max(1, attempts) + 1):
        request = urllib.request.Request(
            EXPO_PUSH_URL,
            data=encoded_messages,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            tickets = payload.get("data", [])
            if isinstance(tickets, dict):
                tickets = [tickets]
            accepted = sum(1 for ticket in tickets if ticket.get("status") == "ok")
            print(
                f"Expo push delivery accepted: {accepted}/{len(messages)} "
                f"code={notification.get('data', {}).get('code', 'UNKNOWN')}",
                flush=True,
            )
            return accepted
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(
                f"Expo push delivery attempt {attempt}/{attempts} failed: {exc}",
                flush=True,
            )
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 30))
    return 0
