"""Serializzazione dei dati utente esponibili tramite le API."""

import sqlite3
from typing import Any


def serialize_public_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "role": row["role"],
        "patient_code": row["patient_code"],
        "fiscal_code": (
            row["fiscal_code"] if "fiscal_code" in row.keys() else None
        ),
        "professional_verified": bool(row["professional_verified"]),
        "account_registered": bool(row["account_registered"]),
        "avatar_data": row["avatar_data"],
    }
