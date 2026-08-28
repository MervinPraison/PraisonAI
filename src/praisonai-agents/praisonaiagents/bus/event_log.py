"""
Durable, queryable per-session lifecycle event log.

The :class:`~praisonaiagents.bus.bus.EventBus` keeps only a bounded in-memory
ring buffer, so its history is lost on restart and cannot be read back per
session. This module adds a durable, append-only *sink* that persists the very
same :class:`~praisonaiagents.bus.event.Event` shapes to SQLite, keyed by
``session_id`` with a monotonic per-session ``seq``, so operators and dashboards
can read one ordered timeline that survives a restart:

    events(session_id, after_seq) -> ordered list[Event]

Design notes (mirrors the durable ``runs/sqlite_ledger.py`` posture):

- **Opt-in.** A bare ``Agent()`` attaches no sink, so the zero-overhead
  in-memory path is untouched. The gateway wires a sink in explicitly.
- **Best-effort.** :meth:`SqliteEventLog.append` never raises into the caller;
  a full/slow/broken log must never break the turn that produced the event.
- **Bounded.** :meth:`SqliteEventLog.prune` trims by age and row count.
- **Reuse, don't reinvent.** Persists the existing ``Event``/``EventType``
  shapes; adds no new status vocabulary.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, List, Optional, Protocol, runtime_checkable

from .._logging import get_logger
from .event import Event, EventType

logger = get_logger(__name__)

__all__ = ["EventLogProtocol", "SqliteEventLog"]


@runtime_checkable
class EventLogProtocol(Protocol):
    """Durable sink for lifecycle events, keyed by session with a cursor.

    Implementations persist events published to an :class:`EventBus` so the
    lifecycle timeline of a session survives a restart and can be read back in
    order with a cursor. ``append`` must be best-effort (never raise into the
    caller).
    """

    def append(self, event: Event) -> None:
        """Durably record ``event``. Best-effort: never raises into caller."""
        ...

    def query(
        self, session_id: str, after_seq: int = 0, limit: int = 500
    ) -> List[Event]:
        """Return events for ``session_id`` with ``seq > after_seq``, ordered."""
        ...

    def prune(self, *, older_than_days: float, max_rows: int) -> int:
        """Delete old/excess rows. Returns the number of rows removed."""
        ...


def _session_id_of(event: Event) -> str:
    """Best-effort resolution of the session an event belongs to.

    Prefers an explicit ``session_id`` in ``data``/``metadata`` and falls back
    to ``event.source`` (many publish sites pass the session id there).
    """
    for container in (event.data, event.metadata):
        if isinstance(container, dict):
            sid = container.get("session_id")
            if sid:
                return str(sid)
    if event.source:
        return str(event.source)
    return ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    session_id    TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    ts            REAL NOT NULL,
    type          TEXT NOT NULL,
    event_id      TEXT,
    source        TEXT,
    data_json     TEXT,
    metadata_json TEXT,
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS event_seq (
    session_id TEXT PRIMARY KEY,
    last_seq   INTEGER NOT NULL
);
"""

_MIGRATIONS = (
    "ALTER TABLE events ADD COLUMN metadata_json TEXT",
)

# Seed the per-session high-water-mark from any pre-existing event rows so a
# database created before ``event_seq`` existed continues numbering above its
# current MAX(seq) instead of colliding on the primary key.
_SEED_HWM = (
    "INSERT INTO event_seq (session_id, last_seq) "
    "SELECT session_id, MAX(seq) FROM events "
    "WHERE session_id NOT IN (SELECT session_id FROM event_seq) "
    "GROUP BY session_id"
)


class SqliteEventLog(EventLogProtocol):
    """Durable, restart-safe lifecycle event log backed by SQLite.

    A durable sibling of :class:`~praisonaiagents.runs.sqlite_ledger.SQLiteRunLedger`.
    One row per event ``(session_id, seq, ts, type, event_id, source, data_json,
    metadata_json)``, append-only, WAL, bounded. Per-session ``seq`` is allocated
    from a persistent ``event_seq`` high-water-mark table so cursors stay
    monotonic across restarts and full prunes. Attach it to a bus with
    ``bus.attach_sink(log)``.

    Args:
        db_path: Path to the SQLite file. Defaults to
            ``<runs_dir>/events.sqlite``. Use ``":memory:"`` for tests.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            from ..paths import get_runs_dir

            runs_dir = get_runs_dir()
            os.makedirs(runs_dir, exist_ok=True)
            db_path = str(runs_dir / "events.sqlite")
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
            self._conn.execute("PRAGMA busy_timeout = 5000")
            if db_path != ":memory:":
                try:
                    self._conn.execute("PRAGMA journal_mode = WAL")
                    self._conn.execute("PRAGMA synchronous = NORMAL")
                except sqlite3.OperationalError:  # pragma: no cover - defensive
                    pass
            self._conn.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Best-effort additive migrations for pre-existing databases."""
        for stmt in _MIGRATIONS:
            try:
                self._conn.execute(stmt)
            except sqlite3.OperationalError:
                # Column already exists (fresh schema) — nothing to do.
                pass
        try:
            self._conn.execute(_SEED_HWM)
        except sqlite3.OperationalError:  # pragma: no cover - defensive
            pass

    # ── public API (EventLogProtocol) ─────────────────────────────────

    def append(self, event: Event) -> None:
        """Durably record ``event``. Best-effort: never raises into caller.

        A monotonic per-session ``seq`` is assigned from a persistent
        high-water-mark table (``event_seq``) inside a serialising
        ``BEGIN IMMEDIATE`` transaction. This makes allocation atomic even when
        two :class:`SqliteEventLog` instances share one database file, and keeps
        the cursor monotonic across restarts *and* after a full prune (deleting
        every row for a session never rewinds its counter).
        """
        try:
            session_id = _session_id_of(event)
            try:
                data_json = json.dumps(event.data)
            except (TypeError, ValueError):
                data_json = json.dumps(event.data, default=str)
            metadata_json = self._dumps_or_none(event.metadata)
            with self._lock:
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                    row = self._conn.execute(
                        "SELECT last_seq FROM event_seq WHERE session_id = ?",
                        (session_id,),
                    ).fetchone()
                    next_seq = (int(row["last_seq"]) if row else 0) + 1
                    self._conn.execute(
                        "INSERT INTO event_seq (session_id, last_seq) VALUES (?, ?) "
                        "ON CONFLICT(session_id) DO UPDATE SET last_seq = excluded.last_seq",
                        (session_id, next_seq),
                    )
                    self._conn.execute(
                        "INSERT INTO events "
                        "(session_id, seq, ts, type, event_id, source, "
                        "data_json, metadata_json) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            session_id,
                            next_seq,
                            float(event.timestamp),
                            event.type,
                            event.id,
                            event.source,
                            data_json,
                            metadata_json,
                        ),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK")
                    except Exception:  # pragma: no cover - defensive
                        pass
                    raise
        except Exception as exc:  # best-effort: never break the originating turn
            logger.debug("SqliteEventLog.append skipped: %s", exc)

    @staticmethod
    def _dumps_or_none(value: Any) -> Optional[str]:
        """Serialise ``value`` to JSON, coercing non-native types; ``None`` if empty."""
        if not value:
            return None
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return json.dumps(value, default=str)

    def query(
        self, session_id: str, after_seq: int = 0, limit: int = 500
    ) -> List[Event]:
        """Return events for ``session_id`` with ``seq > after_seq``, in order."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE session_id = ? AND seq > ? "
                    "ORDER BY seq ASC LIMIT ?",
                    (session_id, int(after_seq), int(limit)),
                ).fetchall()
            return [self._row_to_event(r) for r in rows]
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("SqliteEventLog.query failed: %s", exc)
            return []

    def prune(self, *, older_than_days: float, max_rows: int) -> int:
        """Delete rows older than ``older_than_days`` and beyond ``max_rows``.

        Returns the number of rows deleted. Best-effort; returns ``0`` on error.
        """
        removed = 0
        try:
            with self._lock:
                if older_than_days and older_than_days > 0:
                    cutoff = time.time() - older_than_days * 86400.0
                    cur = self._conn.execute(
                        "DELETE FROM events WHERE ts < ?", (cutoff,)
                    )
                    removed += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                if max_rows and max_rows > 0:
                    total = self._conn.execute(
                        "SELECT COUNT(*) AS c FROM events"
                    ).fetchone()["c"]
                    excess = int(total) - int(max_rows)
                    if excess > 0:
                        cur = self._conn.execute(
                            "DELETE FROM events WHERE rowid IN ("
                            "SELECT rowid FROM events ORDER BY ts ASC LIMIT ?)",
                            (excess,),
                        )
                        removed += (
                            cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                        )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("SqliteEventLog.prune failed: %s", exc)
        return removed

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - defensive
                pass

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        try:
            data = json.loads(row["data_json"]) if row["data_json"] else {}
        except (ValueError, TypeError):
            data = {}
        # Restore caller-provided metadata, then overlay the durable cursor
        # fields (seq, session_id) so correlation/diagnostic keys survive the
        # round trip.
        metadata: dict = {}
        raw_meta = row["metadata_json"] if "metadata_json" in row.keys() else None
        if raw_meta:
            try:
                loaded = json.loads(raw_meta)
                if isinstance(loaded, dict):
                    metadata.update(loaded)
            except (ValueError, TypeError):
                pass
        metadata["seq"] = row["seq"]
        metadata["session_id"] = row["session_id"]
        return Event(
            id=row["event_id"] or "",
            type=row["type"] or EventType.CUSTOM.value,
            data=data,
            timestamp=row["ts"],
            source=row["source"],
            metadata=metadata,
        )
