"""SQLite initialization and lightweight schema migrations."""

import os
import sqlite3


def init_database(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, password_salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient', 'doctor')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS push_tokens (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS doctor_patients (
            doctor_id TEXT NOT NULL, patient_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (doctor_id, patient_id),
            FOREIGN KEY(doctor_id) REFERENCES users(id),
            FOREIGN KEY(patient_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS monitoring_configs (
            patient_id TEXT PRIMARY KEY,
            moderate_deviation_deg REAL NOT NULL,
            marked_deviation_deg REAL NOT NULL,
            persistence_seconds REAL NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(updated_by) REFERENCES users(id)
        );
    """)
    _migrate_users(connection)
    _migrate_monitoring_configs(connection)
    _backfill_users(connection)
    connection.commit()
    return connection


def _migrate_users(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
    migrations = (
        ("patient_code", "TEXT"),
        ("first_name", "TEXT"),
        ("last_name", "TEXT"),
        ("fiscal_code", "TEXT"),
        ("professional_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("avatar_data", "TEXT"),
    )
    for column, definition in migrations:
        if column not in columns:
            connection.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_fiscal_code "
        "ON users(fiscal_code) WHERE fiscal_code IS NOT NULL"
    )


def _migrate_monitoring_configs(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(monitoring_configs)").fetchall()
    }
    if "moderate_roll_deg" not in columns:
        connection.execute("ALTER TABLE monitoring_configs ADD COLUMN moderate_roll_deg REAL")
    if "marked_roll_deg" not in columns:
        connection.execute("ALTER TABLE monitoring_configs ADD COLUMN marked_roll_deg REAL")


def _backfill_users(connection: sqlite3.Connection) -> None:
    users = connection.execute(
        "SELECT id,name,first_name,last_name,role FROM users"
    ).fetchall()
    for user in users:
        if not user["first_name"] or not user["last_name"]:
            parts = user["name"].strip().split(maxsplit=1)
            connection.execute(
                "UPDATE users SET first_name=?,last_name=?,professional_verified=? WHERE id=?",
                (
                    parts[0],
                    parts[1] if len(parts) > 1 else "Utente",
                    1 if user["role"] == "doctor" else 0,
                    user["id"],
                ),
            )

    patients = connection.execute(
        "SELECT id,patient_code FROM users WHERE role='patient' ORDER BY created_at"
    ).fetchall()
    for index, patient in enumerate(patients):
        if not patient["patient_code"]:
            code = (
                "patient-demo-001"
                if index == 0
                else f"patient-{patient['id'].removeprefix('usr_')}"
            )
            connection.execute("UPDATE users SET patient_code=? WHERE id=?", (code, patient["id"]))
