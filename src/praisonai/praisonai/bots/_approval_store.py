"""
Durable approval store for PraisonAI human-in-the-loop approvals.

Pending approvals are normally held only in process memory; if the gateway or
bot restarts while an approval is outstanding the in-flight decision is lost.
This module provides a SQLite-backed :class:`ApprovalStore` that persists
pending approvals with a stable correlation id so they survive a restart and a
late "Allow"/"Deny" tap still resolves.

Design constraints (per PraisonAI principles, mirroring ``_outbox.py``):
  - Wrapper-only — heavy implementation stays out of core SDK.
  - Lazy: sqlite3 is stdlib so no extra dependency.
  - Optional: handlers work exactly as before unless a store is provided.
  - Bounded: resolved entries are evicted by TTL to bound disk growth.
  - Thread-safe: per-instance threading.Lock guards SQLite writes.

Implements :class:`praisonaiagents.approval.ApprovalStoreProtocol`.

Storage schema::

    pending_approvals(
        approval_id TEXT PRIMARY KEY,
        ts REAL,
        expires_at REAL,
        request TEXT,           -- JSON of the ApprovalRequest
        status TEXT,            -- 'pending', 'approved', 'denied', 'expired'
        decision TEXT,          -- JSON of the ApprovalDecision (when resolved)
        approver TEXT,
        resolved_at REAL
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from praisonaiagents.approval import ApprovalDecision, ApprovalRequest

logger = logging.getLogger(__name__)

# 7 days default — long enough to audit, short enough not to blow up disk.
_DEFAULT_TTL_SECONDS = 7 * 86400


def _serialize_request(request: ApprovalRequest) -> str:
    return json.dumps(
        {
            "tool_name": request.tool_name,
            "arguments": request.arguments,
            "risk_level": request.risk_level,
            "agent_name": request.agent_name,
            "session_id": request.session_id,
            "context": request.context,
            "approval_id": request.approval_id,
        },
        default=str,
    )


def _deserialize_request(raw: str) -> ApprovalRequest:
    data = json.loads(raw)
    return ApprovalRequest(
        tool_name=data["tool_name"],
        arguments=data.get("arguments", {}),
        risk_level=data.get("risk_level", "medium"),
        agent_name=data.get("agent_name"),
        session_id=data.get("session_id"),
        context=data.get("context", {}),
        approval_id=data.get("approval_id"),
    )


def _serialize_decision(decision: ApprovalDecision) -> str:
    return json.dumps(
        {
            "approved": decision.approved,
            "reason": decision.reason,
            "modified_args": decision.modified_args,
            "approver": decision.approver,
            "metadata": decision.metadata,
        },
        default=str,
    )


class ApprovalStore:
    """SQLite-backed durable store for pending human-in-the-loop approvals.

    Implements the ``ApprovalStoreProtocol`` from praisonaiagents.

    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        ttl_seconds: Resolved/expired entries older than this are evicted.

    Example::

        from praisonai.bots import ApprovalStore

        store = ApprovalStore(path="~/.praisonai/state/approvals.sqlite")
        await store.persist(req.approval_id, req, expires_at=time.time() + 60)

        # On startup:
        for approval_id, request in await store.list_pending():
            rebind_channel_callback(approval_id, request)
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser()
        self.ttl_seconds = int(ttl_seconds)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Schema ──────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except Exception:
            conn.close()
            raise

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    approval_id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision TEXT,
                    approver TEXT,
                    resolved_at REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_appr_status ON pending_approvals(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_appr_expires ON pending_approvals(expires_at)"
            )
            conn.commit()

    # ── Protocol API (async) ────────────────────────────────────────
    async def persist(
        self,
        approval_id: str,
        request: ApprovalRequest,
        *,
        expires_at: float,
    ) -> None:
        """Durably store a pending approval keyed by ``approval_id``."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._sync_persist, approval_id, request, expires_at
        )

    def _sync_persist(
        self, approval_id: str, request: ApprovalRequest, expires_at: float
    ) -> None:
        with self._lock, closing(self._connect()) as conn:
            self._evict_expired_locked(conn)
            existing = conn.execute(
                "SELECT status FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if existing is not None and existing[0] != "pending":
                # Never clobber a resolved/expired row — that would destroy the
                # durable audit trail. A collision on a full UUID is effectively
                # impossible; if it ever happens we keep the prior decision.
                logger.warning(
                    "Refusing to persist approval %s over resolved status %r",
                    approval_id,
                    existing[0],
                )
                return
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_approvals
                    (approval_id, ts, expires_at, request, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (
                    approval_id,
                    time.time(),
                    float(expires_at),
                    _serialize_request(request),
                ),
            )
            conn.commit()

    async def list_pending(self) -> List[Tuple[str, ApprovalRequest]]:
        """Return outstanding (un-resolved, un-expired) pending approvals."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_load_pending)

    # Backward-compatible alias (pre-rename callers).
    async def load_pending(self) -> List[Tuple[str, ApprovalRequest]]:
        """Deprecated alias for :meth:`list_pending`."""
        return await self.list_pending()

    def _sync_load_pending(self) -> List[Tuple[str, ApprovalRequest]]:
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT approval_id, request FROM pending_approvals
                WHERE status = 'pending' AND expires_at > ?
                ORDER BY ts ASC
                """,
                (now,),
            ).fetchall()
        result: List[Tuple[str, ApprovalRequest]] = []
        for approval_id, raw in rows:
            try:
                result.append((approval_id, _deserialize_request(raw)))
            except Exception:
                logger.exception("Failed to deserialize approval %s", approval_id)
        return result

    async def resolve(self, approval_id: str, decision: ApprovalDecision) -> bool:
        """Record a final decision for ``approval_id`` as an audit trail.

        Returns ``True`` only when a still-pending row was updated, so a stale
        or duplicate resolve (the row already expired/resolved) is reported as
        ``False`` instead of silently appearing successful.

        An explicit terminal state may be supplied via
        ``decision.metadata['terminal']`` (``"approved"`` / ``"denied"`` /
        ``"expired"``); otherwise it is derived from ``decision.approved``.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._sync_resolve, approval_id, decision
        )

    def _sync_resolve(self, approval_id: str, decision: ApprovalDecision) -> bool:
        terminal = (decision.metadata or {}).get("terminal")
        if terminal in ("approved", "denied", "expired"):
            status = terminal
        else:
            status = "approved" if decision.approved else "denied"
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute(
                """
                UPDATE pending_approvals
                SET status = ?, decision = ?, approver = ?, resolved_at = ?
                WHERE approval_id = ? AND status = 'pending'
                """,
                (
                    status,
                    _serialize_decision(decision),
                    decision.approver,
                    time.time(),
                    approval_id,
                ),
            )
            conn.commit()
            updated = int(cur.rowcount or 0) > 0
        if not updated:
            logger.warning(
                "resolve() matched no pending approval %s (already resolved or "
                "expired)",
                approval_id,
            )
        return updated

    # ── Maintenance / introspection ─────────────────────────────────
    async def expire_overdue(self) -> int:
        """Mark pending approvals past their expiry as 'expired'. Returns count."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_expire_overdue)

    def _sync_expire_overdue(self) -> int:
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute(
                """
                UPDATE pending_approvals
                SET status = 'expired', resolved_at = ?
                WHERE status = 'pending' AND expires_at <= ?
                """,
                (now, now),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute(
            """
            DELETE FROM pending_approvals
            WHERE status != 'pending' AND resolved_at IS NOT NULL AND resolved_at <= ?
            """,
            (cutoff,),
        )
        return int(cur.rowcount or 0)

    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored row for ``approval_id`` (for doctor/audit checks)."""
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT approval_id, ts, expires_at, request, status,
                       decision, approver, resolved_at
                FROM pending_approvals WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "approval_id": row[0],
            "ts": row[1],
            "expires_at": row[2],
            "request": row[3],
            "status": row[4],
            "decision": row[5],
            "approver": row[6],
            "resolved_at": row[7],
        }

    def pending_count(self) -> int:
        """Count of currently un-resolved, un-expired pending approvals."""
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM pending_approvals "
                    "WHERE status = 'pending' AND expires_at > ?",
                    (now,),
                ).fetchone()[0]
            )

    def stale_count(self) -> int:
        """Count of stale/orphaned pending approvals past expiry (for doctor)."""
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM pending_approvals "
                    "WHERE status = 'pending' AND expires_at <= ?",
                    (now,),
                ).fetchone()[0]
            )

    def size(self) -> int:
        with self._lock, closing(self._connect()) as conn:
            return int(
                conn.execute("SELECT COUNT(*) FROM pending_approvals").fetchone()[0]
            )

    def purge(self) -> int:
        """Delete all entries. Returns count removed."""
        with self._lock, closing(self._connect()) as conn:
            n = conn.execute("SELECT COUNT(*) FROM pending_approvals").fetchone()[0]
            conn.execute("DELETE FROM pending_approvals")
            conn.commit()
            return int(n)

    def __repr__(self) -> str:
        return (
            f"ApprovalStore(path={str(self.path)!r}, "
            f"size={self.size()}, pending={self.pending_count()}, "
            f"ttl={self.ttl_seconds}s)"
        )


__all__ = ["ApprovalStore"]
