"""
SQLite-backed durable store for background jobs.

A zero-dependency (stdlib ``sqlite3``) implementation of
:class:`~praisonaiagents.background.job_manager.BackgroundJobStore`. Jobs are
persisted to ``<runs_dir>/background_jobs.db`` by default so they survive a
gateway restart; on boot :meth:`BackgroundJobManager.reconcile_on_start` calls
:meth:`list_unreconciled` to reconcile jobs left ``PENDING``/``RUNNING`` by a
crashed process (marked ``LOST``) and to replay undelivered completed jobs.

A durable sibling of :class:`~praisonaiagents.runs.sqlite_ledger.SQLiteRunLedger`
and :class:`~praisonaiagents.bus.event_log.SqliteEventLog` — same posture:
stdlib-only, WAL, a single re-entrant lock guards a shared connection opened
with ``check_same_thread=False`` so the runner's worker threads can persist
safely.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import List, Optional

from .._logging import get_logger
from .job_manager import JobInfo, JobStatus

logger = get_logger(__name__)

__all__ = ["SqliteBackgroundJobStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS background_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    result TEXT,
    error TEXT,
    origin TEXT,
    delivered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status);
"""


def _dumps(value: object) -> Optional[str]:
    """Serialise a value to JSON, never failing on non-JSON-native types."""
    if value is None:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return json.dumps(value, default=str)


class SqliteBackgroundJobStore:
    """Durable, restart-safe background job store backed by SQLite.

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ``<runs_dir>/background_jobs.db``. Use ``":memory:"`` for tests.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from ..paths import get_runs_dir

            runs_dir = get_runs_dir()
            os.makedirs(runs_dir, exist_ok=True)
            db_path = str(runs_dir / "background_jobs.db")
        elif db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            # Wait (instead of failing fast) when another process/connection
            # holds a write lock; overlapping gateway processes share one file.
            self._conn.execute("PRAGMA busy_timeout = 5000")
            # WAL lets readers and a writer proceed concurrently and improves
            # crash durability. Skip for in-memory DBs where it is a no-op.
            if db_path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode = WAL")
                    self._conn.execute("PRAGMA synchronous = NORMAL")
                except sqlite3.OperationalError:  # pragma: no cover - defensive
                    pass
            self._conn.executescript(_SCHEMA)

    # ── public API (BackgroundJobStore) ───────────────────────────────

    def upsert(self, job: JobInfo) -> None:
        """Insert or update the persisted record for ``job`` (keyed by id)."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO background_jobs (
                    job_id, status, created_at, started_at, completed_at,
                    result, error, origin, delivered
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    result=excluded.result,
                    error=excluded.error,
                    origin=excluded.origin,
                    delivered=excluded.delivered
                """,
                (
                    job.job_id,
                    job.status.value,
                    job.created_at,
                    job.started_at,
                    job.completed_at,
                    _dumps(job.result),
                    job.error,
                    _dumps(job.origin) if job.origin else None,
                    1 if job.delivered else 0,
                ),
            )

    def get(self, job_id: str) -> Optional[JobInfo]:
        """Return the persisted :class:`JobInfo`, or ``None`` if unknown."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM background_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def list_unreconciled(self) -> List[JobInfo]:
        """Return jobs needing reconciliation after a restart.

        Jobs left ``PENDING``/``RUNNING`` (orphaned by a crash) and jobs
        ``COMPLETED`` with an ``origin`` that were never ``delivered``. Returned
        oldest-first for deterministic replay.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM background_jobs
                WHERE status IN (?, ?)
                   OR (status = ? AND delivered = 0 AND origin IS NOT NULL)
                ORDER BY created_at ASC
                """,
                (
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                    JobStatus.COMPLETED.value,
                ),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - defensive
                pass

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _loads(raw: Optional[str]) -> object:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    @classmethod
    def _row_to_job(cls, row: sqlite3.Row) -> JobInfo:
        origin = cls._loads(row["origin"])
        return JobInfo(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=cls._loads(row["result"]),
            error=row["error"],
            origin=origin if isinstance(origin, dict) else {},
            delivered=bool(row["delivered"]),
        )
