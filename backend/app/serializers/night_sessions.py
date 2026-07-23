"""Serializzazione stabile delle sessioni di monitoraggio notturno."""

import sqlite3
from datetime import datetime, timezone
from typing import Any


def serialize_night_session(row: sqlite3.Row) -> dict[str, Any]:
    started_at = datetime.fromisoformat(str(row["started_at"]))
    ended_at = (
        datetime.fromisoformat(str(row["ended_at"]))
        if row["ended_at"]
        else datetime.now(timezone.utc)
    )
    duration_seconds = max(
        0,
        round((ended_at - started_at).total_seconds()),
    )
    return {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "device_id": row["device_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "end_reason": row["end_reason"],
        "duration_seconds": duration_seconds,
        "classifier_version": int(row["classifier_version"]),
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
