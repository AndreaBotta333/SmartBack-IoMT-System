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
        CREATE TABLE IF NOT EXISTS device_calibrations (
            device_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            reference_pitch_deg REAL NOT NULL,
            reference_roll_deg REAL NOT NULL,
            algorithm_version INTEGER NOT NULL DEFAULT 1,
            calibrated_at TEXT NOT NULL,
            calibrated_by TEXT,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(calibrated_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            display_name TEXT,
            source_type TEXT NOT NULL DEFAULT 'physical'
                CHECK(source_type IN ('physical', 'simulated')),
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            quality TEXT,
            has_telemetry INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT
        );
        CREATE TABLE IF NOT EXISTS device_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            patient_id TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            released_at TEXT,
            assigned_by TEXT,
            released_by TEXT,
            FOREIGN KEY(device_id) REFERENCES devices(device_id),
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(assigned_by) REFERENCES users(id),
            FOREIGN KEY(released_by) REFERENCES users(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_assignment_device
            ON device_assignments(device_id) WHERE released_at IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_assignment_patient
            ON device_assignments(patient_id) WHERE released_at IS NULL;
        CREATE TABLE IF NOT EXISTS night_monitoring_sessions (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'interrupted')),
            started_at TEXT NOT NULL,
            ended_at TEXT,
            end_reason TEXT,
            created_by TEXT NOT NULL,
            classifier_version INTEGER NOT NULL DEFAULT 1,
            supine_seconds REAL NOT NULL DEFAULT 0,
            prone_seconds REAL NOT NULL DEFAULT 0,
            right_side_seconds REAL NOT NULL DEFAULT 0,
            left_side_seconds REAL NOT NULL DEFAULT 0,
            unknown_seconds REAL NOT NULL DEFAULT 0,
            position_changes INTEGER NOT NULL DEFAULT 0,
            data_gap_seconds REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(device_id) REFERENCES devices(device_id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_night_session_patient
            ON night_monitoring_sessions(patient_id) WHERE status='active';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_night_session_device
            ON night_monitoring_sessions(device_id) WHERE status='active';
        CREATE INDEX IF NOT EXISTS idx_night_sessions_patient_started
            ON night_monitoring_sessions(patient_id, started_at DESC);
    """)
    _migrate_users(connection)
    _migrate_monitoring_configs(connection)
    _migrate_device_calibrations(connection)
    _migrate_devices(connection)
    _backfill_users(connection)
    _seed_physical_shirt(connection)
    connection.commit()
    return connection


def _migrate_device_calibrations(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(device_calibrations)"
        ).fetchall()
    }
    if "algorithm_version" not in columns:
        connection.execute(
            "ALTER TABLE device_calibrations "
            "ADD COLUMN algorithm_version INTEGER NOT NULL DEFAULT 1"
        )


def _migrate_devices(connection: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(devices)").fetchall()
    }
    if "source_type" not in columns:
        connection.execute(
            "ALTER TABLE devices ADD COLUMN source_type TEXT NOT NULL DEFAULT 'physical'"
        )
    if "has_telemetry" not in columns:
        connection.execute(
            "ALTER TABLE devices ADD COLUMN has_telemetry INTEGER NOT NULL DEFAULT 1"
        )
    if "archived_at" not in columns:
        connection.execute("ALTER TABLE devices ADD COLUMN archived_at TEXT")


def _seed_physical_shirt(connection: sqlite3.Connection) -> None:
    now = "1970-01-01T00:00:00+00:00"
    connection.execute(
        "INSERT INTO devices(device_id,display_name,source_type,first_seen_at,last_seen_at,quality,has_telemetry) "
        "VALUES ('tshirt002','Maglia 2','physical',?,?,NULL,0) "
        "ON CONFLICT(device_id) DO UPDATE SET display_name='Maglia 2',source_type='physical'",
        (now, now),
    )


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
