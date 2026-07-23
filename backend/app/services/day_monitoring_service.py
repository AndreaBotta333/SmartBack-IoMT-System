"""Casi d'uso del monitoraggio posturale diurno."""

import sqlite3
from datetime import datetime
from typing import Any, Callable


class DayArchiveUnavailable(Exception):
    pass


class DayMonitoringService:
    def __init__(
        self,
        influx: object | None,
        *,
        threshold_provider: Callable[[sqlite3.Row], Any],
        stale_seconds: float,
    ):
        self.influx = influx
        self.threshold_provider = threshold_provider
        self.stale_seconds = stale_seconds

    def _archive(self):
        if self.influx is None:
            raise DayArchiveUnavailable
        return self.influx

    def history(
        self,
        patient: sqlite3.Row,
        *,
        start: datetime,
        end: datetime,
        minutes: int,
        limit: int,
    ) -> dict[str, Any]:
        result = self._archive().query_posture_history_details(
            patient["patient_code"],
            start=start,
            end=end,
            profile=self.threshold_provider(patient),
            limit=limit,
            stale_seconds=self.stale_seconds,
        )
        return {
            **result,
            "minutes": minutes,
            "patient_id": patient["id"],
            "patient_code": patient["patient_code"],
        }

    def availability(self, patient: sqlite3.Row) -> dict[str, Any]:
        return {
            **self._archive().query_posture_availability(
                patient["patient_code"]
            ),
            "patient_id": patient["id"],
            "patient_code": patient["patient_code"],
        }

    def sessions(self, patient: sqlite3.Row) -> dict[str, Any]:
        return {
            "items": self._archive().query_day_sessions(
                patient["patient_code"]
            ),
            "patient_id": patient["id"],
            "patient_code": patient["patient_code"],
        }

    def statistics(
        self, patient: sqlite3.Row, minutes: int
    ) -> dict[str, Any]:
        normalized_minutes = min(max(minutes, 1), 10_080)
        rows = self._archive().query_posture_history(
            patient["patient_code"],
            normalized_minutes,
            self.threshold_provider(patient),
            600,
        )
        count = len(rows)
        incorrect = sum(1 for row in rows if row["is_incorrect"])
        absolute_values = [
            abs(float(row["deviation_deg"])) for row in rows
        ]
        return {
            "period_minutes": normalized_minutes,
            "samples": count,
            "correct_percentage": (
                round((count - incorrect) * 100 / count, 1)
                if count
                else 0
            ),
            "incorrect_percentage": (
                round(incorrect * 100 / count, 1) if count else 0
            ),
            "average_deviation_deg": (
                round(sum(absolute_values) / count, 1) if count else 0
            ),
            "maximum_deviation_deg": (
                round(max(absolute_values), 1) if count else 0
            ),
        }
