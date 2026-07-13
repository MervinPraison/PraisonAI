"""
SQLite-backed durable run ledger.

A zero-dependency (stdlib ``sqlite3``) default implementation of
:class:`~praisonaiagents.runs.protocols.RunLedgerProtocol`. Runs are persisted
to ``~/.praisonai/runs/ledger.db`` by default so they survive a gateway
restart; on boot the gateway calls :meth:`recover_orphans` to reconcile runs
left active by a crashed process.

Thread-safe (a single re-entrant lock guards a shared connection opened with
``check_same_thread=False``). Heavy channel wake-back lives in the wrapper; this
class only owns durable persistence and orphan reconciliation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import List, Optional

from .._logging import get_logger
from .protocols import ACTIVE_STATUSES, RunLedgerProtocol, RunRecord, RunStatus

logger = get_logger(__name__)

__all__ = ["SQLiteRunLedger"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    thread_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress TEXT,
    terminal_outcome TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
"""


def _dump_metadata(metadata: object) -> str:
    """Serialise metadata to JSON, never failing on non-JSON-native values.

    ``RunRecord.metadata`` is typed ``Dict[str, Any]``; callers may attach a
    ``datetime``, ``set``, ``bytes`` or custom object. Falling back to ``str``
    keeps the run in the durable ledger instead of raising before insert.
    """
    try:
        return json.dumps(metadata)
    except (TypeError, ValueError):
        return json.dumps(metadata, default=str)


class SQLiteRunLedger(RunLedgerProtocol):
    """Durable, restart-safe run ledger backed by SQLite.

    Args:
        db_path: Path to the SQLite database file. Defaults to
            ``~/.praisonai/runs/ledger.db``. Use ``":memory:"`` for tests.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from ..paths import get_runs_dir

            runs_dir = get_runs_dir()
            os.makedirs(runs_dir, exist_ok=True)
            db_path = str(runs_dir / "ledger.db")
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

    # ── public API (RunLedgerProtocol) ────────────────────────────────

    def upsert(self, record: RunRecord) -> None:
        """Insert or update ``record`` (keyed by ``run_id``)."""
        record.updated_at = time.time()
        data = record.to_dict()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs (
                    run_id, agent_id, channel, thread_id, status, progress,
                    terminal_outcome, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    agent_id=excluded.agent_id,
                    channel=excluded.channel,
                    thread_id=excluded.thread_id,
                    status=excluded.status,
                    progress=excluded.progress,
                    terminal_outcome=excluded.terminal_outcome,
                    updated_at=excluded.updated_at,
                    metadata=excluded.metadata
                """,
                (
                    data["run_id"],
                    data["agent_id"],
                    data["channel"],
                    data["thread_id"],
                    data["status"],
                    data["progress"],
                    data["terminal_outcome"],
                    data["created_at"],
                    data["updated_at"],
                    _dump_metadata(data["metadata"]),
                ),
            )

    def get(self, run_id: str) -> Optional[RunRecord]:
        """Return the record for ``run_id`` or ``None`` if unknown."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list_active(self) -> List[RunRecord]:
        """Return all runs still in an active (in-flight) status."""
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        params = [s.value for s in ACTIVE_STATUSES]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM runs WHERE status IN ({placeholders}) "
                "ORDER BY created_at ASC",
                params,
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_all(self, limit: int = 200) -> List[RunRecord]:
        """Return recent runs (newest first) regardless of status."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def recover_orphans(self) -> List[RunRecord]:
        """Mark still-active runs as ``LOST`` and return the affected records.

        Called on gateway boot: any run left in an active status belonged to a
        process that exited without recording a terminal outcome. They are
        reconciled to ``LOST`` so the gateway can notify their origin channels.
        """
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        active_values = [s.value for s in ACTIVE_STATUSES]
        outcome = "lost: gateway restarted mid-run"
        now = time.time()
        recovered: List[RunRecord] = []
        with self._lock:
            # Atomically transition ONLY rows that are still active. A
            # concurrent writer that completed a run (terminal status) between
            # boot and now is not overwritten — the WHERE clause excludes it.
            self._conn.execute(
                f"""
                UPDATE runs
                SET status = ?,
                    terminal_outcome = COALESCE(terminal_outcome, ?),
                    updated_at = ?
                WHERE status IN ({placeholders})
                """,
                [RunStatus.LOST.value, outcome, now, *active_values],
            )
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE status = ? AND updated_at = ?",
                (RunStatus.LOST.value, now),
            ).fetchall()
            recovered = [self._row_to_record(r) for r in rows]
        if recovered:
            logger.info(
                "Recovered %d orphaned run(s) as LOST on ledger boot",
                len(recovered),
            )
        return recovered

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - defensive
                pass

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except (ValueError, TypeError):
            metadata = {}
        return RunRecord.from_dict(
            {
                "run_id": row["run_id"],
                "agent_id": row["agent_id"],
                "channel": row["channel"],
                "thread_id": row["thread_id"],
                "status": row["status"],
                "progress": row["progress"],
                "terminal_outcome": row["terminal_outcome"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": metadata,
            }
        )
