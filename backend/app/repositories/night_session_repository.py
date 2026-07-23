import sqlite3
import threading
from datetime import datetime, timezone


class NightSessionRepository:
    def __init__(self, database: sqlite3.Connection, lock: threading.RLock):
        self.database = database
        self.lock = lock

    def active(self, patient_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM night_monitoring_sessions "
            "WHERE patient_id=? AND status='active' "
            "ORDER BY started_at DESC LIMIT 1",
            (patient_id,),
        ).fetchone()

    def active_assignment(self, patient_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT assignments.device_id,devices.source_type "
            "FROM device_assignments assignments "
            "JOIN devices ON devices.device_id=assignments.device_id "
            "WHERE assignments.patient_id=? AND assignments.released_at IS NULL "
            "AND devices.archived_at IS NULL LIMIT 1",
            (patient_id,),
        ).fetchone()

    def create(
        self,
        session_id: str,
        patient_id: str,
        device_id: str,
        actor_id: str,
    ) -> sqlite3.Row:
        with self.lock:
            self.database.execute(
                "INSERT INTO night_monitoring_sessions("
                "id,patient_id,device_id,status,started_at,created_by) "
                "VALUES (?,?,?,'active',?,?)",
                (
                    session_id,
                    patient_id,
                    device_id,
                    datetime.now(timezone.utc).isoformat(),
                    actor_id,
                ),
            )
            self.database.commit()
        row = self.by_id(session_id)
        if row is None:
            raise RuntimeError("Sessione notturna appena creata non trovata")
        return row

    def complete(
        self,
        session_id: str,
        end_reason: str,
    ) -> sqlite3.Row:
        with self.lock:
            self.database.execute(
                "UPDATE night_monitoring_sessions SET status='completed',"
                "ended_at=?,end_reason=? WHERE id=? AND status='active'",
                (
                    datetime.now(timezone.utc).isoformat(),
                    end_reason,
                    session_id,
                ),
            )
            self.database.commit()
        row = self.by_id(session_id)
        if row is None:
            raise RuntimeError("Sessione notturna completata non trovata")
        return row

    def by_id(self, session_id: str) -> sqlite3.Row | None:
        return self.database.execute(
            "SELECT * FROM night_monitoring_sessions WHERE id=?",
            (session_id,),
        ).fetchone()

    def history(self, patient_id: str, limit: int) -> list[sqlite3.Row]:
        return self.database.execute(
            "SELECT * FROM night_monitoring_sessions WHERE patient_id=? "
            "ORDER BY started_at DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()

    def completed_summary(self, patient_id: str) -> sqlite3.Row:
        return self.database.execute(
            "SELECT COUNT(*) AS session_count,"
            "COALESCE(SUM(supine_seconds),0) AS supine_seconds,"
            "COALESCE(SUM(prone_seconds),0) AS prone_seconds,"
            "COALESCE(SUM(right_side_seconds),0) AS right_side_seconds,"
            "COALESCE(SUM(left_side_seconds),0) AS left_side_seconds,"
            "COALESCE(SUM(unknown_seconds),0) AS unknown_seconds,"
            "COALESCE(SUM(position_changes),0) AS position_changes,"
            "COALESCE(SUM(data_gap_seconds),0) AS data_gap_seconds "
            "FROM night_monitoring_sessions "
            "WHERE patient_id=? AND status!='active'",
            (patient_id,),
        ).fetchone()

    def device_source_type(self, device_id: str) -> str | None:
        row = self.database.execute(
            "SELECT source_type FROM devices WHERE device_id=?", (device_id,)
        ).fetchone()
        return str(row["source_type"]) if row else None
