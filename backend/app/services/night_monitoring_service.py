"""Casi d'uso per avvio, arresto e consultazione del monitoraggio notturno."""

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from app.repositories.night_session_repository import NightSessionRepository


class NightSessionConflict(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NightSessionNotFound(Exception):
    pass


class NightMonitoringService:
    def __init__(
        self,
        repository: NightSessionRepository,
        *,
        influx: object | None,
        messaging: object | None,
        serializer: Callable[[sqlite3.Row], dict[str, Any]],
    ):
        self.repository = repository
        self.influx = influx
        self.messaging = messaging
        self.serializer = serializer

    def active(self, patient_id: str) -> sqlite3.Row | None:
        return self.repository.active(patient_id)

    def status(self, patient: sqlite3.Row) -> dict[str, Any]:
        session = self.active(str(patient["id"]))
        return {
            "mode": "night" if session else "day",
            "active": session is not None,
            "session": self.serializer(session) if session else None,
        }

    def history(
        self, patient: sqlite3.Row, limit: int
    ) -> dict[str, Any]:
        normalized_limit = min(max(limit, 1), 200)
        rows = self.repository.history(str(patient["id"]), normalized_limit)
        return {
            "patient_id": patient["id"],
            "patient_code": patient["patient_code"],
            "items": [self.serializer(row) for row in rows],
            "count": len(rows),
        }

    def history_summary(self, patient: sqlite3.Row) -> dict[str, Any]:
        row = self.repository.completed_summary(str(patient["id"]))
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

    def session(self, session_id: str) -> tuple[sqlite3.Row, dict[str, Any]]:
        row = self.repository.by_id(session_id)
        if row is None:
            raise NightSessionNotFound
        result = self.serializer(row)
        result["positions"] = (
            self.influx.query_night_positions(session_id)
            if self.influx is not None
            else []
        )
        return row, result

    def start(self, patient: sqlite3.Row, actor: sqlite3.Row) -> dict[str, Any]:
        if self.repository.active(str(patient["id"])) is not None:
            raise NightSessionConflict("Monitoraggio notturno già attivo")
        assignment = self.repository.active_assignment(str(patient["id"]))
        if assignment is None:
            raise NightSessionConflict(
                "Nessuna maglia attiva assegnata al paziente"
            )
        session_id = (
            f"night_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_"
            f"{secrets.token_hex(6)}"
        )
        try:
            session = self.repository.create(
                session_id,
                str(patient["id"]),
                str(assignment["device_id"]),
                str(actor["id"]),
            )
        except sqlite3.IntegrityError as error:
            self.repository.database.rollback()
            raise NightSessionConflict(
                "La maglia è già impegnata in un monitoraggio notturno"
            ) from error
        if self.influx is not None:
            self.influx.persist_night_session_state(
                patient_code=str(patient["patient_code"]),
                session_id=session_id,
                device_id=str(assignment["device_id"]),
                active=True,
            )
        if assignment["source_type"] == "simulated" and self.messaging:
            self.messaging.publish_simulation_scenario(
                str(assignment["device_id"]), "night-cycle"
            )
        return {
            "mode": "night",
            "active": True,
            "session": self.serializer(session),
        }

    def stop(self, patient: sqlite3.Row, end_reason: str) -> dict[str, Any]:
        session = self.repository.active(str(patient["id"]))
        if session is None:
            raise NightSessionConflict("Nessun monitoraggio notturno attivo")
        completed = self.repository.complete(str(session["id"]), end_reason)
        if self.influx is not None:
            self.influx.persist_night_session_state(
                patient_code=str(patient["patient_code"]),
                session_id=str(session["id"]),
                device_id=str(session["device_id"]),
                active=False,
            )
        if (
            self.repository.device_source_type(str(session["device_id"]))
            == "simulated"
            and self.messaging
        ):
            self.messaging.publish_simulation_scenario(
                str(session["device_id"]), "day-cycle"
            )
        return {
            "mode": "day",
            "active": False,
            "session": self.serializer(completed),
        }
