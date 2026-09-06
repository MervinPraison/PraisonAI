"""Durable per-identity token-usage sink for PraisonAI gateways (Issue #4894).

A public multi-user gateway runs one shared :class:`~praisonaiagents.agent.Agent`
in front of many end users. To answer *"how much has this identity cost me,
cumulatively, and does it survive a restart?"* and to enforce a budget *before*
the next turn runs, usage must be persisted keyed by the gateway identity.

The only :class:`~praisonaiagents.telemetry.protocols.TokenUsageSinkProtocol`
implementations shipped so far are ``NoOpTokenUsageSink`` (zero overhead) and
``InMemoryTokenUsageSink`` (lost on restart, not per-identity). This module adds
:class:`SqliteTokenUsageSink`, a durable, queryable ledger keyed by canonical
gateway identity + scope, built on the standard-library ``sqlite3`` (no new
dependency, no heavy import on the common telemetry path).

It pairs with
:class:`~praisonaiagents.gateway.protocols.WindowedSpendBudgetPolicy`: the sink
answers :meth:`SqliteTokenUsageSink.spent` (cumulative USD for an identity+scope
over a window) and the policy turns that into an admit decision.

Example::

    from praisonaiagents.telemetry.durable_sink import SqliteTokenUsageSink

    sink = SqliteTokenUsageSink("~/.praisonai/usage.db")
    sink.record(identity="tg:123", scope="telegram", cost_usd=0.02)
    sink.spent(identity="tg:123", scope="telegram", since=window_start)  # -> 0.02
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    identity      TEXT    NOT NULL,
    scope         TEXT    NOT NULL DEFAULT '',
    model         TEXT    NOT NULL DEFAULT '',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL    NOT NULL DEFAULT 0.0,
    ts            REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_token_usage_identity_scope_ts
    ON token_usage (identity, scope, ts);
"""


class SqliteTokenUsageSink:
    """Durable, per-identity token-usage ledger backed by ``sqlite3`` (stdlib).

    Implements the existing
    :class:`~praisonaiagents.telemetry.protocols.TokenUsageSinkProtocol` so it
    can be attached to the global token collector exactly like the in-memory
    sink, while additionally keying every record by a gateway ``identity`` and
    ``scope`` so cumulative spend survives restarts and is queryable per user.

    Args:
        db_path: Filesystem path to the SQLite database. ``~`` is expanded and
            parent directories are created. Use ``":memory:"`` for an ephemeral
            (test) database.

    The instance is safe to share across threads: a single connection is guarded
    by a lock (SQLite's own file locking handles cross-process access).
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = (
            db_path
            if db_path == ":memory:"
            else os.path.abspath(os.path.expanduser(str(db_path)))
        )
        if self.db_path != ":memory:":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False + our own lock lets a shared gateway sink be
        # used from the async event loop and worker threads safely.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- write path ---------------------------------------------------------

    def record(
        self,
        *,
        identity: str,
        scope: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: Optional[int] = None,
        cost_usd: float = 0.0,
        ts: Optional[float] = None,
    ) -> None:
        """Append a usage record for a gateway identity.

        This is the gateway-facing entry point (the natural attribution key is
        the canonical user id). ``persist`` adapts the generic
        :class:`TokenUsageSinkProtocol` signature onto this.
        """
        in_tok = int(input_tokens or 0)
        out_tok = int(output_tokens or 0)
        tot = int(total_tokens) if total_tokens is not None else in_tok + out_tok
        row = (
            str(identity),
            str(scope or ""),
            str(model or ""),
            in_tok,
            out_tok,
            tot,
            float(cost_usd or 0.0),
            float(ts if ts is not None else time.time()),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO token_usage "
                "(identity, scope, model, input_tokens, output_tokens, "
                "total_tokens, cost_usd, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            self._conn.commit()

    def persist(
        self,
        task_id: str,
        agent_name: str,
        model: str,
        metrics: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """:class:`TokenUsageSinkProtocol` entry point.

        The gateway identity/scope/cost are read from ``metadata`` when present
        (``identity``, ``scope``, ``cost_usd``) so the generic collector path
        can attribute spend without a bespoke signature. Falls back to the
        agent name as identity so nothing is silently dropped.
        """
        meta = metadata or {}
        identity = str(meta.get("identity") or agent_name or "")
        self.record(
            identity=identity,
            scope=str(meta.get("scope") or ""),
            model=model or "",
            input_tokens=getattr(metrics, "input_tokens", 0) or 0,
            output_tokens=getattr(metrics, "output_tokens", 0) or 0,
            total_tokens=getattr(metrics, "total_tokens", None),
            cost_usd=float(meta.get("cost_usd") or 0.0),
        )

    # -- read path ----------------------------------------------------------

    def spent(
        self,
        *,
        identity: str,
        scope: Optional[str] = None,
        since: float = 0.0,
    ) -> float:
        """Cumulative USD spent by ``identity`` (optionally within ``scope``).

        Args:
            identity: Canonical gateway identity to sum spend for.
            scope: When provided, restrict to this scope (channel/tenant);
                when ``None``, sum across all scopes for the identity.
            since: Only count records with ``ts >= since`` — pass the window
                start (e.g. ``policy.window_start(now)``) to enforce a rolling
                budget window.
        """
        query = (
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS spent "
            "FROM token_usage WHERE identity = ? AND ts >= ?"
        )
        params: List[Any] = [str(identity), float(since)]
        if scope is not None:
            query += " AND scope = ?"
            params.append(str(scope))
        with self._lock:
            cur = self._conn.execute(query, params)
            row = cur.fetchone()
        return float(row["spent"] if row is not None else 0.0)

    def oldest_spend_ts(
        self,
        *,
        identity: str,
        scope: Optional[str] = None,
        since: float = 0.0,
    ) -> Optional[float]:
        """Timestamp of the earliest in-window charge for ``identity``.

        Feeds :class:`~praisonaiagents.gateway.protocols.WindowedSpendBudgetPolicy`
        so a rejected caller gets an accurate ``retry_after_seconds`` hint
        (when this earliest charge ages out of the window). Returns ``None``
        when there is no spend in the window.
        """
        query = (
            "SELECT MIN(ts) AS oldest FROM token_usage "
            "WHERE identity = ? AND ts >= ? AND cost_usd > 0"
        )
        params: List[Any] = [str(identity), float(since)]
        if scope is not None:
            query += " AND scope = ?"
            params.append(str(scope))
        with self._lock:
            cur = self._conn.execute(query, params)
            row = cur.fetchone()
        if row is None or row["oldest"] is None:
            return None
        return float(row["oldest"])

    def usage(
        self,
        *,
        identity: str,
        scope: Optional[str] = None,
        since: float = 0.0,
    ) -> Dict[str, Any]:
        """Aggregate spend + token totals for ``identity`` (for ``/usage``)."""
        query = (
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS cost_usd, "
            "COALESCE(SUM(input_tokens), 0) AS input_tokens, "
            "COALESCE(SUM(output_tokens), 0) AS output_tokens, "
            "COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            "COUNT(*) AS records "
            "FROM token_usage WHERE identity = ? AND ts >= ?"
        )
        params: List[Any] = [str(identity), float(since)]
        if scope is not None:
            query += " AND scope = ?"
            params.append(str(scope))
        with self._lock:
            cur = self._conn.execute(query, params)
            row = cur.fetchone()
        if row is None:
            return {
                "identity": str(identity),
                "scope": scope,
                "cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "records": 0,
            }
        return {
            "identity": str(identity),
            "scope": scope,
            "cost_usd": float(row["cost_usd"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "records": int(row["records"]),
        }

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SqliteTokenUsageSink":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
