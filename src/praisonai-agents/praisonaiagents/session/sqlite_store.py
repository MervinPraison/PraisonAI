"""
SQLite/FTS5-backed session store for scalable cross-session recall.

``DefaultSessionStore.search`` reads and lexically scans *every* session JSON
file on disk for each query — an ``O(all sessions)`` directory scan that
degrades linearly as a long-lived gateway bot accumulates thousands of
sessions (Issue #2927).

``SqliteSessionStore`` keeps the durable JSON transcripts as the source of
truth (so it is fully backward-compatible and inspectable), but additionally
maintains a lazily-built stdlib ``sqlite3`` FTS5 index of message content. A
query becomes a *bounded* index lookup (``MATCH ... ORDER BY bm25`` when FTS5
is available) rather than a full-directory scan. Only the matched sessions'
JSON is then read to build anchored hits, reusing the parent store's
bookend / automated-demotion / lineage-dedup logic.

Dependency-free: uses only the standard library (``sqlite3`` is lazy-imported).
If ``sqlite3`` or FTS5 is unavailable, it transparently falls back to the
parent store's substring scan, so recall never breaks.

Usage::

    from praisonaiagents.session import SqliteSessionStore

    store = SqliteSessionStore(db_path="~/.praisonai/sessions.db")
    agent = Agent(..., session_store=store)  # opt-in; Default stays fallback

    store.search("billing migration")  # bounded index lookup + anchored hits
"""

import os
import threading
from typing import Any, Dict, List, Optional

from praisonaiagents._logging import get_logger

from .store import DefaultSessionStore, SessionData

logger = get_logger(__name__)


class SqliteSessionStore(DefaultSessionStore):
    """Indexed session store: JSON transcripts + a SQLite/FTS5 recall index.

    Inherits all persistence behaviour from :class:`DefaultSessionStore`
    (JSON files, file locking, retention/compaction) and layers a durable
    full-text index on top so ``search`` is a bounded index lookup.
    """

    def __init__(
        self,
        session_dir: Optional[str] = None,
        db_path: Optional[str] = None,
        **kwargs: Any,
    ):
        """Initialize the indexed store.

        Args:
            session_dir: Directory for session JSON files (as in the parent).
            db_path: Path to the SQLite index file. Defaults to a
                ``sessions_index.db`` alongside ``session_dir``. Use
                ``":memory:"`` for an ephemeral in-process index.
            **kwargs: Forwarded to :class:`DefaultSessionStore`.
        """
        super().__init__(session_dir=session_dir, **kwargs)
        if db_path is None:
            db_path = os.path.join(self.session_dir, "sessions_index.db")
        elif db_path != ":memory:":
            db_path = os.path.expanduser(db_path)
        self.db_path = db_path
        self._db_lock = threading.RLock()
        self._conn = None
        self._fts_available = False
        self._db_ready = False
        self._backfilled = False

    # ── index lifecycle ───────────────────────────────────────────────

    def _connect(self):
        """Open (once) the SQLite connection and create the schema lazily."""
        if self._db_ready:
            return self._conn
        with self._db_lock:
            if self._db_ready:
                return self._conn
            try:
                import sqlite3  # lazy import — stdlib, no heavy dependency
            except Exception as exc:  # pragma: no cover - sqlite3 always present
                logger.warning("sqlite3 unavailable, recall falls back to scan: %s", exc)
                self._db_ready = True
                return None

            try:
                if self.db_path != ":memory:":
                    os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
                conn = sqlite3.connect(
                    self.db_path, check_same_thread=False, isolation_level=None
                )
                self._fts_available = self._init_schema(conn)
                self._conn = conn
            except Exception as exc:
                logger.warning("Failed to open session index, falling back: %s", exc)
                self._conn = None
            self._db_ready = True
            return self._conn

    def _init_schema(self, conn) -> bool:
        """Create the FTS5 (or fallback) schema. Returns True if FTS5 works."""
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS session_fts "
                "USING fts5(session_id UNINDEXED, content)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS session_meta ("
                "session_id TEXT PRIMARY KEY, updated_at TEXT)"
            )
            self._init_route_schema(conn)
            return True
        except Exception as exc:
            logger.info("FTS5 not available (%s); using LIKE fallback index.", exc)
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS session_fts ("
                    "session_id TEXT PRIMARY KEY, content TEXT)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS session_meta ("
                    "session_id TEXT PRIMARY KEY, updated_at TEXT)"
                )
                self._init_route_schema(conn)
                return False
            except Exception:
                self._conn = None
                raise

    @staticmethod
    def _init_route_schema(conn) -> None:
        """Create the indexed gateway/agent routing table.

        Maps ``gateway_session_id`` and ``agent_id`` to a ``session_id`` so the
        gateway hot-path lookups (``get_by_gateway_session`` /
        ``list_sessions_by_gateway_agent``) become O(1)/O(log n) index reads
        instead of an ``os.listdir`` + JSON-parse of every stored session
        (Issue #2956).
        """
        conn.execute(
            "CREATE TABLE IF NOT EXISTS session_route ("
            "  session_id TEXT PRIMARY KEY,"
            "  gateway_session_id TEXT,"
            "  agent_id TEXT"
            ")"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_gateway "
            "ON session_route(gateway_session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_route_agent "
            "ON session_route(agent_id)"
        )

    @staticmethod
    def _flatten(session: SessionData) -> str:
        """Concatenate a session's message content for indexing."""
        parts = []
        for msg in session.messages:
            content = getattr(msg, "content", "")
            if content:
                parts.append(str(content))
        return "\n".join(parts)

    def _index_session(self, session: SessionData) -> None:
        """Insert/replace a session's content in the index (best-effort)."""
        conn = self._connect()
        if conn is None:
            return
        content = self._flatten(session)
        sid = session.session_id
        gateway_session_id = getattr(session, "gateway_session_id", None)
        agent_id = getattr(session, "agent_id", None)
        try:
            with self._db_lock:
                conn.execute("DELETE FROM session_fts WHERE session_id = ?", (sid,))
                conn.execute(
                    "INSERT INTO session_fts (session_id, content) VALUES (?, ?)",
                    (sid, content),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO session_meta (session_id, updated_at) "
                    "VALUES (?, ?)",
                    (sid, session.updated_at),
                )
                # Keep the gateway/agent routing index in sync so inbound
                # routing is an indexed lookup, not a full-directory scan.
                if gateway_session_id or agent_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO session_route "
                        "(session_id, gateway_session_id, agent_id) "
                        "VALUES (?, ?, ?)",
                        (sid, gateway_session_id, agent_id),
                    )
                else:
                    conn.execute(
                        "DELETE FROM session_route WHERE session_id = ?", (sid,)
                    )
        except Exception as exc:  # never let indexing break a write
            logger.debug("Session index update failed for %s: %s", sid, exc)

    def _deindex_session(self, session_id: str) -> None:
        conn = self._connect()
        if conn is None:
            return
        try:
            with self._db_lock:
                conn.execute("DELETE FROM session_fts WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM session_meta WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM session_route WHERE session_id = ?", (session_id,))
        except Exception as exc:
            logger.debug("Session de-index failed for %s: %s", session_id, exc)

    def _ensure_backfilled(self) -> None:
        """Backfill the index from existing JSON transcripts exactly once.

        Guarded by a one-time flag rather than by an empty-index check: a
        single ``add_message`` on a *new* session could otherwise make the
        index non-empty and permanently skip backfilling pre-existing JSON
        transcripts, silently omitting legacy sessions from search results.
        Only sessions not already present in the index are (re)indexed, so the
        pass is cheap on a warm index.
        """
        if self._backfilled:
            return
        with self._db_lock:
            if self._backfilled:
                return
            self._backfilled = True
            self._reindex_all()

    def _indexed_ids(self) -> set:
        """Return the set of session_ids already fully indexed.

        A session counts as indexed only if it is present in *both* the content
        index (``session_meta``) *and* the routing index (``session_route``).
        This closes a migration gap: an existing store upgraded from a prior
        release (content index populated, ``session_route`` created empty) would
        otherwise have its already-content-indexed sessions skipped by backfill,
        leaving ``session_route`` empty and breaking gateway routing. Requiring a
        route row forces those sessions to be re-indexed so their route rows are
        populated. Backfill runs at most once (guarded by ``_backfilled``), so
        this stays a cheap one-time pass.
        """
        conn = self._connect()
        if conn is None:
            return set()
        try:
            with self._db_lock:
                meta_rows = conn.execute(
                    "SELECT session_id FROM session_meta"
                ).fetchall()
                route_rows = conn.execute(
                    "SELECT session_id FROM session_route"
                ).fetchall()
            meta_ids = {r[0] for r in meta_rows}
            route_ids = {r[0] for r in route_rows}
            return meta_ids & route_ids
        except Exception:
            return set()

    def _reindex_all(self) -> None:
        """Backfill the index from existing JSON transcripts (skip indexed)."""
        try:
            filenames = os.listdir(self.session_dir)
        except (IOError, OSError):
            return
        already = self._indexed_ids()
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            sid = filename[:-5]
            if sid in already:
                continue
            try:
                session = self._read_session_fresh(sid)
            except Exception:
                continue
            self._index_session(session)

    # ── write path: keep the index in sync ────────────────────────────

    def _save_session(self, session: SessionData) -> bool:
        ok = super()._save_session(session)
        if ok:
            self._index_session(session)
        return ok

    def _modify_session_locked(self, session_id, mutator, **kwargs) -> bool:
        """Refresh the index after any locked read-modify-write.

        Transcript-replacing paths such as ``set_chat_history`` and
        ``append_compaction_checkpoint`` mutate the persisted JSON through this
        helper *without* going via ``_save_session``. Overriding here keeps the
        FTS index in sync with those replacements so search never returns stale
        or missing content.
        """
        ok = super()._modify_session_locked(session_id, mutator, **kwargs)
        if ok:
            try:
                self._index_session(self._read_session_fresh(session_id))
            except Exception as exc:
                logger.debug("Post-modify index refresh failed for %s: %s", session_id, exc)
        return ok

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
    ) -> bool:
        ok = super().add_message(
            session_id,
            role,
            content,
            metadata,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        if ok:
            try:
                self._index_session(self._read_session_fresh(session_id))
            except Exception as exc:
                logger.debug("Post-add index refresh failed for %s: %s", session_id, exc)
        return ok

    def clear_session(self, session_id: str) -> bool:
        ok = super().clear_session(session_id)
        if ok:
            self._deindex_session(session_id)
        return ok

    def delete_session(self, session_id: str) -> bool:
        ok = super().delete_session(session_id)
        if ok:
            self._deindex_session(session_id)
        return ok

    # ── read path: bounded index lookup + anchored hits ───────────────

    def _candidate_ids(self, query: str, limit: int) -> Optional[List[str]]:
        """Return matching session_ids via the index, or None to fall back."""
        conn = self._connect()
        if conn is None:
            return None
        # Backfill any pre-existing JSON transcripts into the index exactly
        # once, so legacy sessions are never silently omitted from results.
        self._ensure_backfilled()

        # Over-fetch candidates so lineage-dedup / automated-demotion can still
        # promote the right interactive sessions into the final ``limit``.
        fetch = max(limit * 5, limit)
        try:
            with self._db_lock:
                if self._fts_available:
                    match = self._to_fts_query(query)
                    rows = conn.execute(
                        "SELECT session_id FROM session_fts WHERE session_fts "
                        "MATCH ? ORDER BY bm25(session_fts) LIMIT ?",
                        (match, fetch),
                    ).fetchall()
                else:
                    like = "%" + query.replace("%", "").replace("_", "") + "%"
                    rows = conn.execute(
                        "SELECT session_id FROM session_fts WHERE content LIKE ? "
                        "LIMIT ?",
                        (like, fetch),
                    ).fetchall()
        except Exception as exc:
            logger.debug("Index query failed (%s); falling back to scan.", exc)
            return None
        return [r[0] for r in rows]

    @staticmethod
    def _to_fts_query(query: str) -> str:
        """Turn free text into a safe FTS5 MATCH expression (OR of terms)."""
        terms = [t for t in "".join(
            c if (c.isalnum() or c.isspace()) else " " for c in query
        ).split() if t]
        if not terms:
            return '""'
        return " OR ".join('"%s"' % t for t in terms)

    # ── gateway/agent routing: indexed key → session lookup ───────────

    def get_by_gateway_session(self, gateway_session_id: str) -> Optional[SessionData]:
        """Resolve a session by ``gateway_session_id`` via the indexed route.

        Overrides the parent's O(N) ``os.listdir`` + JSON-parse-every-file scan
        with a single indexed ``SELECT`` on ``session_route`` so inbound routing
        latency is independent of the number of stored sessions (Issue #2956).
        Falls back to the parent scan if the index is unavailable.
        """
        conn = self._connect()
        if conn is None:
            return super().get_by_gateway_session(gateway_session_id)
        self._ensure_backfilled()
        try:
            with self._db_lock:
                row = conn.execute(
                    "SELECT session_id FROM session_route "
                    "WHERE gateway_session_id = ?",
                    (gateway_session_id,),
                ).fetchone()
        except Exception as exc:
            logger.debug("Route lookup failed (%s); falling back to scan.", exc)
            return super().get_by_gateway_session(gateway_session_id)
        if row is None:
            return None
        try:
            return self._read_session_fresh(row[0])
        except Exception:
            return None

    def list_sessions_by_gateway_agent(self, agent_id: str, limit: int = 50) -> List[str]:
        """List session IDs for a gateway agent via the indexed route.

        Overrides the parent's full-directory scan with an indexed ``SELECT``
        on ``session_route`` (Issue #2956). Falls back to the parent scan if the
        index is unavailable.
        """
        conn = self._connect()
        if conn is None:
            return super().list_sessions_by_gateway_agent(agent_id, limit)
        self._ensure_backfilled()
        try:
            with self._db_lock:
                rows = conn.execute(
                    "SELECT session_id FROM session_route WHERE agent_id = ? "
                    "LIMIT ?",
                    (agent_id, limit),
                ).fetchall()
        except Exception as exc:
            logger.debug("Route lookup failed (%s); falling back to scan.", exc)
            return super().list_sessions_by_gateway_agent(agent_id, limit)
        return [r[0] for r in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        window: int = 5,
    ) -> List[Any]:
        """Indexed full-text search with anchored, demoted, deduped results.

        Uses the SQLite/FTS5 index to find candidate sessions (bounded lookup)
        and then reuses the parent store's per-session scoring so results carry
        the same ``match_window`` + ``bookends``, automated demotion, and
        lineage dedup. Falls back to the parent scan if the index is
        unavailable.
        """
        from .protocols import SessionHit

        query = (query or "").strip()
        if not query:
            return []

        candidate_ids = self._candidate_ids(query, limit)
        if candidate_ids is None:
            return super().search(query, limit=limit, window=window)
        if not candidate_ids:
            return []

        needle = query.lower()
        terms = [t for t in needle.split() if t]
        hits: List[tuple] = []

        for sid in candidate_ids:
            filepath = self._get_session_path(sid)
            try:
                import json

                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
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
                session_id=data.get("session_id", sid),
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
