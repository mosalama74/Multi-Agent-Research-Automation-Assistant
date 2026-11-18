from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunStore:
    """SQLite audit log for workflow runs and explicitly approved actions."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("APP_DB_PATH", "data/runs.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_count INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    report_markdown TEXT NOT NULL,
                    email_to TEXT,
                    email_sent INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS action_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                )"""
            )

    def save_run(self, result: Any) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO runs
                (run_id, created_at, task, status, source_count, duration_seconds, report_markdown, error_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.run_id,
                    created_at,
                    result.task,
                    result.status,
                    len(result.sources),
                    float(result.duration_seconds),
                    result.report_markdown,
                    "\n".join(result.errors) if result.errors else None,
                ),
            )
            conn.execute(
                "INSERT INTO action_events (run_id, created_at, action_type, outcome, details) VALUES (?, ?, ?, ?, ?)",
                (result.run_id, created_at, "workflow", result.status, json.dumps({"source_count": len(result.sources)})),
            )

    def log_email(self, run_id: str, recipient: str, sent: bool, details: str = "") -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET email_to=?, email_sent=? WHERE run_id=?",
                (recipient, 1 if sent else 0, run_id),
            )
            conn.execute(
                "INSERT INTO action_events (run_id, created_at, action_type, outcome, details) VALUES (?, ?, ?, ?, ?)",
                (run_id, timestamp, "email", "sent" if sent else "failed", details[:1000]),
            )

    def recent_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_id, created_at, task, status, source_count, duration_seconds, email_to, email_sent, error_summary FROM runs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def metrics(self) -> dict[str, float | int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS successful, AVG(duration_seconds) AS average_duration, SUM(email_sent) AS emails_sent FROM runs"
            ).fetchone()
            total = int(row["total"] or 0)
            successful = int(row["successful"] or 0)
            return {
                "total_runs": total,
                "successful_runs": successful,
                "success_rate_pct": round(100.0 * successful / total, 1) if total else 0.0,
                "average_duration_seconds": round(float(row["average_duration"] or 0.0), 2),
                "emails_sent": int(row["emails_sent"] or 0),
            }
