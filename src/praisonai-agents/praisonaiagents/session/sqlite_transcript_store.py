"""
SQLite-backed transcript store for concurrent multi-channel gateways.

``DefaultSessionStore`` persists each session as one JSON file guarded by a
cross-process ``FileLock``. Under a busy gateway (many users, many channels,
multi-instance) that flat-file model is the concurrency weak point: hot
sessions serialise on a single file lock, and ``list``/``search``/gateway
routing fall back to an ``os.listdir`` + JSON-parse-every-file directory scan.
Every other PraisonAI runtime store (inbound journal, dead-letter queue,
delivery state, kanban) already uses SQLite — transcripts were the outlier
(Issue #3407).

``SqliteTranscriptStore`` stores each session's durable record as one row in a
SQLite table (WAL mode → concurrent readers, transactional single-row writes,
no whole-directory rewrite) keyed by ``session_id`` and indexed by
``gateway_session_id`` / ``agent_id`` / ``updated_at``. It is a drop-in for
``DefaultSessionStore``: it *subclasses* it and overrides only the persistence
primitives, so all retention/compaction, message API, search scoring, bookends,
lineage-dedup and window/recent logic are inherited unchanged. The public
``Session`` / store API is identical.

Dependency-free: uses only the standard library (``sqlite3`` is lazy-imported).
If ``sqlite3`` is unavailable it raises at construction, so callers can fall
back to the JSON store explicitly.

Usage::

    from praisonaiagents.session import SqliteTranscriptStore

    store = SqliteTranscriptStore(db_path="~/.praisonai/sessions/sessions.db")
    agent = Agent(..., session_store=store)      # drop-in for DefaultSessionStore
    store.add_message("s1", "user", "hi")        # single-row transactional write
    store.search("refund")                        # indexed candidate lookup
"""

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from praisonaiagents._logging import get_logger

from .store import DefaultSessionStore, SessionData

logger = get_logger(__name__)


class SqliteTranscriptStore(DefaultSessionStore):
    """Session transcripts in SQLite (WAL): one row per session.

    Drop-in replacement for :class:`DefaultSessionStore`. Replaces the
    per-session JSON file + ``FileLock`` persistence with transactional
    single-row SQLite writes and indexed lookups, inheriting every other
    behaviour (retention/compaction, search scoring, bookends, gateway/agent
    linkage) from the parent.
    """

    def __init__(
        self,
        session_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        **kwargs: Any,
    ):
        """Initialize the SQLite transcript store.

        Args:
            session_dir: Retained for API compatibility with the parent and to
                derive a default ``db_path``. No JSON files are written here.
            db_path: Path to the SQLite database file. Defaults to
                ``sessions.db`` alongside ``session_dir``. Use ``":memory:"``
                for an ephemeral in-process store.
            **kwargs: Forwarded to :class:`DefaultSessionStore` (retention,
                active_window, max_messages, lock_timeout).
        """
        super().__init__(session_dir=session_dir, **kwargs)
        if db_path is None:
            db_path = os.path.join(self.session_dir, "sessions.db")
        elif db_path != ":memory:":
            db_path = os.path.expanduser(db_path)
        self.db_path = db_path
        self._db_lock = threading.RLock()
        self._conn = None
        self._db_ready = False

    # ── connection / schema ───────────────────────────────────────────

    def _connect(self):
        """Open (once) the SQLite connection in WAL mode and create schema."""
        if self._db_ready:
            return self._conn
        with self._db_lock:
            if self._db_ready:
                return self._conn
            import sqlite3  # lazy import — stdlib, no heavy dependency

            if self.db_path != ":memory:":
                os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            conn = sqlite3.connect(
                self.db_path, check_same_thread=False, isolation_level=None
            )
            try:
                # WAL lets readers proceed concurrently with a writer.
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=%d" % int(self.lock_timeout * 1000))
            except Exception:  # pragma: no cover - PRAGMA best-effort
                pass
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "  session_id TEXT PRIMARY KEY,"
                "  data TEXT NOT NULL,"
                "  agent_name TEXT,"
                "  gateway_session_id TEXT,"
                "  agent_id TEXT,"
                "  updated_at TEXT"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_gateway "
                "ON sessions(gateway_session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_agent "
                "ON sessions(agent_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_agent_name "
                "ON sessions(agent_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_updated "
                "ON sessions(updated_at)"
            )
            self._conn = conn
            self._db_ready = True
            self._migrate_legacy_json(conn)
            return self._conn

    def _migrate_legacy_json(self, conn) -> None:
        """One-time import of legacy per-session JSON files into the DB.

        When an existing file/JSON deployment upgrades to the SQLite default,
        the prior transcripts would otherwise be invisible (a fresh, empty
        ``sessions.db`` opens beside the old ``*.json`` files) — session resume
        would treat existing sessions as new (Issue #3407 follow-up). This
        imports any ``*.json`` transcripts that live alongside the DB exactly
        once, only for rows not already present, so upgrading preserves durable
        history. It is a no-op for ``:memory:`` and for fresh installs.
        """
        if self.db_path == ":memory:":
            return
        session_dir = self.session_dir
        if not session_dir or not os.path.isdir(session_dir):
            return
        try:
            filenames = [f for f in os.listdir(session_dir) if f.endswith(".json")]
        except OSError:
            return
        if not filenames:
            return
        try:
            existing = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            if existing and existing[0]:
                return  # DB already populated; do not re-import
        except Exception:  # pragma: no cover - best-effort guard
            return
        imported = 0
        for filename in filenames:
            filepath = os.path.join(session_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            try:
                session = SessionData.from_dict(data)
            except Exception:  # pragma: no cover - tolerate malformed legacy files
                continue
            if self._write_row(session, conn=conn):
                imported += 1
        if imported:
            logger.info(
                "Imported %d legacy JSON session(s) from %s into SQLite store",
                imported,
                session_dir,
            )

    # ── row read/write helpers ────────────────────────────────────────

    def _read_row(self, session_id: str, conn=None) -> Optional[Dict[str, Any]]:
        own_lock = conn is None
        if conn is None:
            conn = self._connect()
        if own_lock:
            with self._db_lock:
                row = conn.execute(
                    "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def _write_row(self, session: SessionData, conn=None) -> bool:
        own_lock = conn is None
        if conn is None:
            conn = self._connect()
        data = session.to_dict()
        try:
            payload = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.error("Failed to serialise session %s: %s", session.session_id, exc)
            return False
        params = (
            session.session_id,
            payload,
            getattr(session, "agent_name", None),
            getattr(session, "gateway_session_id", None),
            getattr(session, "agent_id", None),
            getattr(session, "updated_at", None),
        )
        sql = (
            "INSERT OR REPLACE INTO sessions "
            "(session_id, data, agent_name, gateway_session_id, agent_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        try:
            if own_lock:
                with self._db_lock:
                    conn.execute(sql, params)
            else:
                conn.execute(sql, params)
            return True
        except Exception as exc:
            logger.error("Failed to write session %s: %s", session.session_id, exc)
            return False

    # ── override persistence primitives (no files, no FileLock) ───────

    def _load_session_from_disk(self, session_id: str, filepath: str) -> SessionData:
        data = self._read_row(session_id)
        if data is not None:
            return SessionData.from_dict(data)
        return SessionData(session_id=session_id)

    def _read_session_fresh(self, session_id: str) -> SessionData:
        session = self._load_session_from_disk(session_id, "")
        with self._lock:
            self._cache[session_id] = session
        return session

    def _load_session(self, session_id: str) -> SessionData:
        data = self._read_row(session_id)
        if data is not None:
            session = SessionData.from_dict(data)
            with self._lock:
                self._cache[session_id] = session
            return session
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]
            session = SessionData(session_id=session_id)
            self._cache[session_id] = session
            return session

    def _save_session(self, session: SessionData) -> bool:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._enforce_window(session)
        with self._db_lock:
            if not self._write_row(session):
                return False
            with self._lock:
                self._cache[session.session_id] = session
            return True

    def _modify_session_locked(
        self,
        session_id: str,
        mutator,
        *,
        error_label: str = "modify session",
    ) -> bool:
        """Read-modify-write a session row atomically.

        The SELECT and INSERT run inside a single ``BEGIN IMMEDIATE``
        transaction so the whole read-modify-write is serialized *across
        processes* (SQLite grabs the database RESERVED write lock at ``BEGIN
        IMMEDIATE`` and holds it until COMMIT). Without this a second gateway
        process could read the same row before this one's INSERT and silently
        drop the earlier append — the exact multi-gateway lost-update the
        parent's cross-process ``FileLock`` prevents. The process-local
        ``_db_lock`` only serializes threads within one process, so it is not
        sufficient on its own.
        """
        conn = self._connect()
        with self._db_lock:
            try:
                conn.execute("BEGIN IMMEDIATE")
            except Exception as exc:
                logger.error("Failed to begin %s %s: %s", error_label, session_id, exc)
                return False
            try:
                data = self._read_row(session_id, conn=conn)
                session = (
                    SessionData.from_dict(data)
                    if data is not None
                    else SessionData(session_id=session_id)
                )
                mutator(session)
                session.updated_at = datetime.now(timezone.utc).isoformat()
                self._enforce_window(session)
                if not self._write_row(session, conn=conn):
                    conn.execute("ROLLBACK")
                    logger.error("Failed to %s %s", error_label, session_id)
                    return False
                conn.execute("COMMIT")
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except Exception:  # pragma: no cover - rollback best-effort
                    pass
                logger.error("Failed to %s %s: %s", error_label, session_id, exc)
                return False
            with self._lock:
                self._cache[session_id] = session
            return True

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
    ) -> bool:
        from .store import SessionMessage
        import time

        message = SessionMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )

        def _apply(session: SessionData) -> None:
            session.messages.append(message)

        return self._modify_session_locked(
            session_id, _apply, error_label="add message to session"
        )

    def delete_session(self, session_id: str) -> bool:
        conn = self._connect()
        with self._lock:
            self._cache.pop(session_id, None)
        try:
            with self._db_lock:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?", (session_id,)
                )
            return True
        except Exception as exc:
            logger.error("Failed to delete session %s: %s", session_id, exc)
            return False

    def session_exists(self, session_id: str) -> bool:
        conn = self._connect()
        with self._db_lock:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1", (session_id,)
            ).fetchone()
        return row is not None

    # ── indexed listings / lookups (replace directory scans) ──────────

    def _all_rows(self):
        conn = self._connect()
        with self._db_lock:
            rows = conn.execute(
                "SELECT data FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        for row in rows:
            try:
                yield json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        sessions = []
        for data in self._all_rows():
            meta = data.get("metadata") or {}
            sid = data.get("session_id", "")
            sessions.append({
                "session_id": sid,
                "id": sid,
                "agent_name": data.get("agent_name"),
                "agent_id": data.get("agent_id") or meta.get("agent_id"),
                "source": data.get("source") or meta.get("source"),
                "parent_id": data.get("parent_id") or meta.get("parent_id"),
                "parent_session_id": data.get("parent_session_id") or meta.get("parent_session_id"),
                "agent_key": data.get("agent_key") or meta.get("agent_key"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(data.get("messages", [])),
                "model": data.get("model") or data.get("llm") or meta.get("model"),
                "total_tokens": data.get("total_tokens") or data.get("token_count") or meta.get("total_tokens"),
                "cost": data.get("cost") or meta.get("cost"),
            })
            if len(sessions) >= limit:
                break
        return sessions

    def list_sessions_by_agent(self, agent_name: str, limit: int = 50) -> List[str]:
        conn = self._connect()
        with self._db_lock:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE agent_name = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (agent_name, limit),
            ).fetchall()
        return [r[0] for r in rows]

    def get_by_gateway_session(self, gateway_session_id: str) -> Optional[SessionData]:
        conn = self._connect()
        with self._db_lock:
            row = conn.execute(
                "SELECT data FROM sessions WHERE gateway_session_id = ? LIMIT 1",
                (gateway_session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return SessionData.from_dict(json.loads(row[0]))
        except (json.JSONDecodeError, TypeError):
            return None

    def list_sessions_by_gateway_agent(self, agent_id: str, limit: int = 50) -> List[str]:
        conn = self._connect()
        with self._db_lock:
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE agent_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [r[0] for r in rows]

    # ── search: indexed candidate lookup + inherited scoring ──────────

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        window: int = 5,
    ) -> List[Any]:
        """Full-text search over transcripts using an indexed candidate lookup.

        Candidate sessions are found with a bounded ``LIKE`` query against the
        stored JSON payload (not an ``os.listdir`` scan); the parent store's
        per-session scoring, bookends, automated-demotion and lineage-dedup are
        then reused verbatim so results are identical in shape.
        """
        from .protocols import SessionHit

        query = (query or "").strip()
        if not query:
            return []

        needle = query.lower()
        terms = [t for t in needle.split() if t]

        conn = self._connect()
        like = "%" + query.replace("%", "").replace("_", "") + "%"
        fetch = max(limit * 5, limit)
        with self._db_lock:
            rows = conn.execute(
                "SELECT data FROM sessions WHERE lower(data) LIKE lower(?) "
                "ORDER BY updated_at DESC LIMIT ?",
                (like, fetch),
            ).fetchall()

        hits: List[tuple] = []
        for row in rows:
            try:
                data = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue
            messages = data.get("messages", [])
            if not isinstance(messages, list):
                continue

            best_index = -1
            best_score = 0.0
            total_score = 0.0
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                content = str(msg.get("content", ""))
                if not content:
                    continue
                lowered = content.lower()
                score = 0.0
                if needle in lowered:
                    score += 2.0
                score += sum(1.0 for term in terms if term in lowered)
                total_score += score
                if score > best_score:
                    best_score = score
                    best_index = idx

            if best_index < 0:
                continue

            start = max(0, best_index - window)
            end = min(len(messages), best_index + window + 1)
            context = [
                {
                    "index": i,
                    "role": messages[i].get("role", ""),
                    "content": messages[i].get("content", ""),
                    "timestamp": messages[i].get("timestamp"),
                }
                for i in range(start, end)
                if isinstance(messages[i], dict)
            ]

            if self._is_automated_session(data, messages):
                total_score *= self.AUTOMATED_DEMOTION

            hit = SessionHit(
                session_id=data.get("session_id", ""),
                title=self._session_title(data),
                when=data.get("updated_at") or data.get("created_at"),
                snippet=self._make_snippet(
                    messages[best_index].get("content", ""), query
                ),
                score=total_score,
                anchor_index=best_index,
                messages=context,
                bookends=self._bookends(messages, self.BOOKEND_SIZE),
            )
            hits.append((self._lineage_key(data), hit))

        hits.sort(key=lambda item: (item[1].score, item[1].when or ""), reverse=True)

        deduped: List[Any] = []
        seen_lineage: set = set()
        for lineage, hit in hits:
            if lineage is not None:
                if lineage in seen_lineage:
                    continue
                seen_lineage.add(lineage)
            deduped.append(hit)
            if len(deduped) >= limit:
                break
        return deduped
