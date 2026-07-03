"""
Async approval-request queue for the PraisonAI gateway.

Manages pending approval requests, resolution, and a durable, scoped
allow-always permission list so users don't have to re-approve the same tool
repeatedly — and so those grants survive a gateway restart and stay scoped to
the agent they were granted for.

This is a *heavy implementation* and lives in the wrapper, not the core SDK.
The core SDK only provides :class:`ApprovalProtocol` in
``praisonaiagents.approval.protocols``.

Durability & scoping
--------------------
Historically the allow-list was a bare in-memory ``Set[str]`` of tool names,
so every "allow always" grant was lost on restart and applied to *every* agent
with *any* arguments. This module now backs the allow-list with an optional
SQLite :class:`ScopedAllowlistStore` (mirroring the durable, fail-closed
``bots/_approval_store.py`` pattern) that keys grants by
``(agent_id, tool_name, arg_signature)``:

  - **Durable** — grants survive restart / hot-reload (SQLite WAL).
  - **Scoped** — a grant for one agent does not authorise every agent; an
    optional argument signature can narrow it further.
  - **Fail-closed rehydration** — on startup the manager reads persisted grants
    back into an explicit allow-list rather than defaulting open.

Backward compatibility is preserved: the previous name-only API
(``allowlist.add("tool")`` / ``"tool" in allowlist``) still works and is
treated as an "any agent" (``agent_id="*"``) grant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import secrets
import threading
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING, Union

if TYPE_CHECKING:  # pragma: no cover - typing only
    from praisonaiagents.approval import ApprovalStoreProtocol

logger = logging.getLogger(__name__)

# Sentinel agent id meaning "applies to any agent". Used for the legacy
# name-only grant path so old callers keep working.
ANY_AGENT = "*"

# 90 days default — long enough to be useful, bounded so the store can't grow
# without limit. 0 (or negative) disables TTL eviction.
_DEFAULT_GRANT_TTL_SECONDS = 90 * 86400


def _default_store_path() -> Path:
    """Return the default durable allow-list SQLite path.

    Honours ``PRAISONAI_HOME`` (falling back to ``~/.praisonai``) and lives
    under ``state/gateway/approvals.sqlite`` per the SDK's SQLite-first
    runtime-state guidance.
    """
    base = os.environ.get("PRAISONAI_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".praisonai"
    return root / "state" / "gateway" / "approvals.sqlite"


def make_arg_signature(arguments: Optional[Dict[str, Any]]) -> Optional[str]:
    """Build a stable, order-independent signature for a set of arguments.

    Returns ``None`` for empty/absent arguments (i.e. an unsigned, tool-level
    grant). The signature is deterministic across processes so a persisted
    grant matches a later identical call.
    """
    if not arguments:
        return None
    import hashlib
    import json

    try:
        canonical = json.dumps(arguments, sort_keys=True, default=str)
    except Exception:
        canonical = repr(sorted((str(k), str(v)) for k, v in arguments.items()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class PendingRequest:
    """A tool-execution approval request waiting for resolution."""

    request_id: str
    tool_name: str
    arguments: Dict[str, Any]
    agent_name: str = ""
    risk_level: str = "medium"
    created_at: float = field(default_factory=time.time)
    # Resolved via the asyncio Future
    _future: Optional[asyncio.Future] = field(default=None, repr=False)
    # Store the event loop at registration time for thread-safe resolution
    _loop: Optional[asyncio.AbstractEventLoop] = field(default=None, repr=False)


@dataclass
class Resolution:
    """Human decision for a pending request."""

    approved: bool
    reason: str = ""
    allow_always: bool = False  # add tool to permanent allow-list
    # If True, an ``allow_always`` grant is scoped to the requesting agent (and
    # optionally its argument signature). If False, the grant applies to any
    # agent (legacy behaviour). Default True = safe-by-default scoping.
    scope_to_agent: bool = True
    # If True, also key the grant by the request's argument signature.
    scope_to_args: bool = False


# ── Durable, scoped allow-list store ─────────────────────────────────

class ScopedAllowlistStore:
    """SQLite-backed durable store of scoped "allow always" grants.

    Grants are keyed by ``(agent_id, tool_name, arg_signature)`` where
    ``agent_id`` may be :data:`ANY_AGENT` (``"*"``) for a legacy global grant
    and ``arg_signature`` may be ``None`` for a tool-level (argument-agnostic)
    grant. This mirrors the durable, fail-closed discipline of
    ``bots/_approval_store.py``.

    Thread-safe: a per-instance :class:`threading.Lock` guards SQLite writes so
    both the async ``register`` path and the sync ``resolve`` path are safe.

    Args:
        path: SQLite file path. Parent dirs are created. Defaults to
            ``~/.praisonai/state/gateway/approvals.sqlite``.
        ttl_seconds: Grants older than this are evicted (0 disables eviction).
    """

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        *,
        ttl_seconds: int = _DEFAULT_GRANT_TTL_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser() if path is not None else _default_store_path()
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
                CREATE TABLE IF NOT EXISTS allow_grants (
                    agent_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arg_signature TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    approver TEXT,
                    PRIMARY KEY (agent_id, tool_name, arg_signature)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_grant_tool ON allow_grants(tool_name)"
            )
            conn.commit()

    # ── Mutations ───────────────────────────────────────────────────
    def add(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
        approver: Optional[str] = None,
    ) -> None:
        """Persist a scoped allow-always grant (idempotent)."""
        sig = arg_signature or ""
        with self._lock, closing(self._connect()) as conn:
            self._evict_expired_locked(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO allow_grants
                    (agent_id, tool_name, arg_signature, created_at, approver)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, tool_name, sig, time.time(), approver),
            )
            conn.commit()

    def allows(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
    ) -> bool:
        """Return True if a matching grant exists.

        A call is allowed when there is a grant that is at least as broad as the
        call: an ``ANY_AGENT`` grant covers every agent, and a tool-level
        (empty ``arg_signature``) grant covers any arguments.
        """
        sig = arg_signature or ""
        agent_keys = {agent_id, ANY_AGENT}
        sig_keys = {"", sig} if sig else {""}
        placeholders_a = ",".join("?" for _ in agent_keys)
        placeholders_s = ",".join("?" for _ in sig_keys)
        # Enforce TTL on read so an expired grant never authorises a call, even
        # when queried directly against the store.
        cutoff = (time.time() - self.ttl_seconds) if self.ttl_seconds > 0 else None
        ttl_clause = " AND created_at > ?" if cutoff is not None else ""
        params = [tool_name, *agent_keys, *sig_keys]
        if cutoff is not None:
            params.append(cutoff)
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT 1 FROM allow_grants
                WHERE tool_name = ?
                  AND agent_id IN ({placeholders_a})
                  AND arg_signature IN ({placeholders_s})
                  {ttl_clause}
                LIMIT 1
                """,
                params,
            ).fetchone()
        return row is not None

    def revoke(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
    ) -> bool:
        """Remove a specific grant. Returns True if a row was deleted.

        If ``arg_signature`` is ``None`` all argument-scoped grants for the
        ``(agent_id, tool_name)`` pair are removed.
        """
        with self._lock, closing(self._connect()) as conn:
            if arg_signature is None:
                cur = conn.execute(
                    "DELETE FROM allow_grants WHERE agent_id = ? AND tool_name = ?",
                    (agent_id, tool_name),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM allow_grants WHERE agent_id = ? AND tool_name = ? "
                    "AND arg_signature = ?",
                    (agent_id, tool_name, arg_signature),
                )
            conn.commit()
            return int(cur.rowcount or 0) > 0

    def revoke_tool(self, tool_name: str) -> bool:
        """Remove every grant for ``tool_name`` across all agents."""
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM allow_grants WHERE tool_name = ?", (tool_name,)
            )
            conn.commit()
            return int(cur.rowcount or 0) > 0

    # ── Introspection ───────────────────────────────────────────────
    def list(self, *, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List grants, optionally filtered to one ``agent_id``."""
        with self._lock, closing(self._connect()) as conn:
            if self._evict_expired_locked(conn):
                # Persist the eviction; otherwise sqlite rolls back the implicit
                # transaction on connection close and expired rows never leave.
                conn.commit()
            if agent_id is None:
                rows = conn.execute(
                    "SELECT agent_id, tool_name, arg_signature, created_at, approver "
                    "FROM allow_grants ORDER BY tool_name, agent_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT agent_id, tool_name, arg_signature, created_at, approver "
                    "FROM allow_grants WHERE agent_id = ? ORDER BY tool_name",
                    (agent_id,),
                ).fetchall()
        return [
            {
                "agent_id": r[0],
                "tool_name": r[1],
                "arg_signature": r[2] or None,
                "created_at": r[3],
                "approver": r[4],
            }
            for r in rows
        ]

    def list_tools(self) -> List[str]:
        """Return the sorted set of tool names with any grant (legacy view)."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT DISTINCT tool_name FROM allow_grants ORDER BY tool_name"
            ).fetchall()
        return [r[0] for r in rows]

    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        if self.ttl_seconds <= 0:
            return 0
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute(
            "DELETE FROM allow_grants WHERE created_at <= ?", (cutoff,)
        )
        return int(cur.rowcount or 0)

    def purge(self) -> int:
        with self._lock, closing(self._connect()) as conn:
            n = conn.execute("SELECT COUNT(*) FROM allow_grants").fetchone()[0]
            conn.execute("DELETE FROM allow_grants")
            conn.commit()
            return int(n)


# ── Permission allow-list ────────────────────────────────────────────

class PermissionAllowlist:
    """Scoped, optionally-durable allow-list of permitted tool grants.

    When a user resolves a request with ``allow_always=True`` the corresponding
    grant is recorded here so future calls skip approval. Grants are keyed by
    ``(agent_id, tool_name, arg_signature)`` — a grant for one agent does not
    silently authorise every other agent.

    Durability: when constructed with ``durable=True`` (the default) grants are
    persisted to a SQLite :class:`ScopedAllowlistStore` and survive a restart.
    A fast in-memory mirror is kept for hot-path checks; it is rehydrated from
    the store on construction (fail-closed: only persisted grants are re-applied).

    Backward compatibility: the historical name-only API is preserved.
    ``add("tool")`` / ``"tool" in allowlist`` / ``remove("tool")`` / ``list()``
    keep working and are treated as :data:`ANY_AGENT` grants.
    """

    def __init__(
        self,
        *,
        durable: bool = True,
        store: Optional[ScopedAllowlistStore] = None,
        path: Optional[Union[str, Path]] = None,
    ) -> None:
        self._lock = threading.Lock()
        # In-memory mirror of grant keys (agent_id, tool_name, arg_signature)
        self._allowed: Set[tuple] = set()
        self._store: Optional[ScopedAllowlistStore] = None
        if durable:
            try:
                self._store = store or ScopedAllowlistStore(path=path)
                self._rehydrate()
            except Exception:
                # Fail-closed on the persistence path: if the store cannot be
                # opened we fall back to a purely in-memory allow-list rather
                # than crashing the gateway. Grants simply won't survive restart.
                logger.exception(
                    "Durable allow-list store unavailable; falling back to "
                    "in-memory only (grants will not survive restart)"
                )
                self._store = None

    # ── Rehydration (fail-closed) ────────────────────────────────────
    def _rehydrate(self) -> None:
        if self._store is None:
            return
        for grant in self._store.list():
            key = (
                grant["agent_id"],
                grant["tool_name"],
                grant.get("arg_signature") or "",
            )
            self._allowed.add(key)
        if self._allowed:
            logger.info(
                "Rehydrated %d durable allow-list grant(s) from %s",
                len(self._allowed), self._store.path,
            )

    # ── Scoped API ───────────────────────────────────────────────────
    def add_scoped(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
        approver: Optional[str] = None,
    ) -> None:
        """Add a scoped grant, persisting it when durable."""
        key = (agent_id, tool_name, arg_signature or "")
        with self._lock:
            self._allowed.add(key)
        if self._store is not None:
            try:
                self._store.add(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    arg_signature=arg_signature,
                    approver=approver,
                )
            except Exception:
                logger.exception(
                    "Failed to persist allow-list grant (agent=%s tool=%s)",
                    agent_id, tool_name,
                )

    def allows(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
    ) -> bool:
        """Return True if a matching grant covers this call.

        A grant covers the call when it is at least as broad: an
        :data:`ANY_AGENT` grant covers every agent and a tool-level grant
        (empty signature) covers any arguments.
        """
        sig = arg_signature or ""
        with self._lock:
            for a in (agent_id, ANY_AGENT):
                if (a, tool_name, "") in self._allowed:
                    return True
                if sig and (a, tool_name, sig) in self._allowed:
                    return True
        return False

    def revoke_scoped(
        self,
        *,
        agent_id: str = ANY_AGENT,
        tool_name: str,
        arg_signature: Optional[str] = None,
    ) -> bool:
        """Remove a scoped grant. Returns True if anything was removed."""
        removed = False
        with self._lock:
            if arg_signature is None:
                for key in list(self._allowed):
                    if key[0] == agent_id and key[1] == tool_name:
                        self._allowed.discard(key)
                        removed = True
            else:
                key = (agent_id, tool_name, arg_signature)
                if key in self._allowed:
                    self._allowed.discard(key)
                    removed = True
        if self._store is not None:
            try:
                store_removed = self._store.revoke(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    arg_signature=arg_signature,
                )
                removed = removed or store_removed
            except Exception:
                logger.exception(
                    "Failed to revoke persisted grant (agent=%s tool=%s)",
                    agent_id, tool_name,
                )
        return removed

    def list_scoped(self, *, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List grants as dicts, optionally filtered by ``agent_id``."""
        if self._store is not None:
            try:
                return self._store.list(agent_id=agent_id)
            except Exception:
                logger.exception("Failed to list persisted grants; using memory")
        with self._lock:
            items = [
                {
                    "agent_id": a,
                    "tool_name": t,
                    "arg_signature": s or None,
                }
                for (a, t, s) in self._allowed
                if agent_id is None or a == agent_id
            ]
        return sorted(items, key=lambda d: (d["tool_name"], d["agent_id"]))

    # ── Legacy name-only API (backward compatible) ───────────────────
    def add(self, tool_name: str) -> None:
        """Legacy: add a global (any-agent) tool grant."""
        self.add_scoped(agent_id=ANY_AGENT, tool_name=tool_name)

    def remove(self, tool_name: str) -> bool:
        """Legacy: remove every grant for ``tool_name`` (all agents)."""
        removed = False
        with self._lock:
            for key in list(self._allowed):
                if key[1] == tool_name:
                    self._allowed.discard(key)
                    removed = True
        if self._store is not None:
            try:
                removed = self._store.revoke_tool(tool_name) or removed
            except Exception:
                logger.exception("Failed to revoke persisted tool %s", tool_name)
        return removed

    def __contains__(self, tool_name: str) -> bool:
        """Legacy: True if any global grant exists for this tool name."""
        return self.allows(agent_id=ANY_AGENT, tool_name=tool_name)

    def list(self) -> List[str]:
        """Legacy: sorted tool names granted globally (``ANY_AGENT``).

        Only global grants are returned so this preserves its historical
        meaning of "tools that skip approval for every agent". Agent-scoped
        grants are exposed via :meth:`list_scoped` / the ``grants`` view.
        """
        with self._lock:
            return sorted(
                {key[1] for key in self._allowed if key[0] == ANY_AGENT}
            )


# ── Main manager ─────────────────────────────────────────────────────

class ExecApprovalManager:
    """Async queue of pending approval requests.

    Gateway endpoints call :meth:`register` to create a request and ``await``
    the returned ``asyncio.Future``.  A separate endpoint (or bot command)
    calls :meth:`resolve` to fulfil the Future.

    Thread-safety:
        Uses ``threading.Lock`` (not asyncio.Lock) so both async ``register()``
        and sync ``resolve()`` can safely mutate ``_pending``.

    Args:
        ttl: Seconds before a pending request auto-expires (default 300 = 5 min).
        durable: Persist "allow always" grants to SQLite so they survive
            restart (default True).
        allowlist_path: Optional override for the durable store path.

    Example::

        manager = ExecApprovalManager(ttl=120)

        # Agent thread: register and wait
        request_id, future = await manager.register(
            tool_name="shell_exec",
            arguments={"cmd": "rm -rf /tmp/cache"},
            agent_name="cleanup-agent",
        )

        # API endpoint: resolve
        manager.resolve(request_id, Resolution(approved=True))

        # Agent thread: future completes
        resolution = await future
    """

    def __init__(
        self,
        ttl: float = 300.0,
        store: Optional["ApprovalStoreProtocol"] = None,
        *,
        durable: bool = True,
        allowlist_path: Optional[Union[str, Path]] = None,
        allowlist: Optional[PermissionAllowlist] = None,
    ) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()  # threading.Lock for cross-thread safety
        self._pending: Dict[str, PendingRequest] = {}
        self._store = store
        # Strong refs to in-flight durable-write tasks so the event loop's
        # weak task tracking cannot GC them mid-execution (see CPython docs
        # for asyncio.create_task).
        self._bg_tasks: Set[asyncio.Task] = set()
        self.allowlist = allowlist or PermissionAllowlist(
            durable=durable, path=allowlist_path,
        )

    # ── Durable rehydration ───────────────────────────────────────────

    async def rehydrate(self) -> int:
        """Reload outstanding approvals from the durable store on boot.

        Rehydrated requests have no live ``asyncio.Future`` (the awaiting
        caller was lost with the previous process) but remain visible via
        :meth:`list_pending` and resolvable via :meth:`resolve`, which records
        the decision to the durable audit trail. Returns the number of
        approvals reloaded. A no-op when no store is configured.
        """
        if self._store is None:
            return 0
        try:
            pending = await self._store.list_pending()
        except Exception:
            logger.exception("Failed to rehydrate pending approvals from store")
            return 0

        count = 0
        with self._lock:
            for approval_id, req in pending:
                if approval_id in self._pending:
                    continue
                # Preserve the ORIGINAL deadline. The store persisted
                # ``expires_at`` at registration; deriving created_at back from
                # it keeps the in-memory TTL aligned with the durable expiry so
                # a restart cannot extend an almost-expired approval by a full
                # ttl. Fall back to now only if the store can't surface it.
                created_at = time.time()
                get = getattr(self._store, "get", None)
                if callable(get):
                    try:
                        row = get(approval_id)
                        if row and row.get("expires_at") is not None:
                            created_at = float(row["expires_at"]) - self._ttl
                    except Exception:
                        logger.debug(
                            "Could not read stored expiry for %s", approval_id
                        )
                self._pending[approval_id] = PendingRequest(
                    request_id=approval_id,
                    tool_name=req.tool_name,
                    arguments=req.arguments,
                    agent_name=req.agent_name or "",
                    risk_level=req.risk_level,
                    created_at=created_at,
                )
                count += 1
        if count:
            logger.info("Rehydrated %d pending gateway approval(s)", count)
        return count

    # ── Registration ──────────────────────────────────────────────────

    async def register(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_name: str = "",
        risk_level: str = "medium",
    ) -> tuple:
        """Create a pending request and return ``(request_id, future)``.

        If a matching allow-always grant exists (scoped to this agent, or a
        legacy global grant), the future is resolved immediately with
        ``approved=True``.
        """
        # Fast path: already permanently allowed (scoped to this agent, its
        # argument signature, or a legacy global grant).
        agent_id = agent_name or ANY_AGENT
        arg_sig = make_arg_signature(arguments)
        if self.allowlist.allows(
            agent_id=agent_id, tool_name=tool_name, arg_signature=arg_sig,
        ):
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            future.set_result(Resolution(approved=True, reason="allow-always"))
            return ("auto", future)

        request_id = self._make_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        req = PendingRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            agent_name=agent_name,
            risk_level=risk_level,
            _future=future,
            _loop=loop,  # capture loop at registration for thread-safe resolve
        )

        with self._lock:
            self._prune()
            self._pending[request_id] = req

        # Durably persist so a restart can rehydrate this pending approval.
        if self._store is not None:
            try:
                from praisonaiagents.approval import ApprovalRequest

                await self._store.persist(
                    request_id,
                    ApprovalRequest(
                        tool_name=tool_name,
                        arguments=arguments,
                        risk_level=risk_level,
                        agent_name=agent_name or None,
                        approval_id=request_id,
                    ),
                    expires_at=time.time() + self._ttl,
                )
            except Exception:
                logger.exception(
                    "Failed to persist approval %s to durable store", request_id
                )

        logger.info(
            "Approval request registered: %s (tool=%s, agent=%s)",
            request_id, tool_name, agent_name,
        )
        return (request_id, future)

    # ── Resolution ────────────────────────────────────────────────────

    def resolve(self, request_id: str, resolution: Resolution) -> bool:
        """Resolve a pending request.  Returns ``True`` if found.

        This is intentionally synchronous so it can be called from any
        thread (e.g. a Starlette request handler).
        """
        with self._lock:
            req = self._pending.pop(request_id, None)

        if req is None:
            return False

        if resolution.allow_always:
            # Scope the grant safely-by-default: to the requesting agent unless
            # the resolver explicitly widened it, and optionally to its
            # argument signature. ``ANY_AGENT`` (a global grant) is only used
            # when the resolver explicitly opts out of agent scoping — never as
            # a silent fallback for a request that lacks an agent identity.
            if resolution.scope_to_agent and not req.agent_name:
                logger.warning(
                    "Skipping scoped allow-always grant for tool '%s': no agent "
                    "identity on the request. Set scope_to_agent=False to grant "
                    "globally.",
                    req.tool_name,
                )
            else:
                agent_id = req.agent_name if resolution.scope_to_agent else ANY_AGENT
                arg_sig = (
                    make_arg_signature(req.arguments)
                    if resolution.scope_to_args
                    else None
                )
                self.allowlist.add_scoped(
                    agent_id=agent_id,
                    tool_name=req.tool_name,
                    arg_signature=arg_sig,
                    approver="gateway:human",
                )
                logger.info(
                    "Tool '%s' added to allow-always list (agent=%s, args=%s)",
                    req.tool_name, agent_id,
                    "scoped" if arg_sig else "any",
                )

        if req._future and not req._future.done() and req._loop:
            req._loop.call_soon_threadsafe(
                req._future.set_result, resolution,
            )

        # Record the decision to the durable audit trail (best-effort).
        self._record_resolution(request_id, resolution)

        logger.info(
            "Approval resolved: %s -> %s",
            request_id,
            "approved" if resolution.approved else "denied",
        )
        return True

    def _record_resolution(self, request_id: str, resolution: Resolution) -> None:
        """Persist a decision to the durable store (sync, best-effort).

        Called from :meth:`resolve`, which may run on any thread. The store's
        ``resolve`` is async, so we schedule it on a running loop when one is
        available and otherwise run it synchronously.
        """
        if self._store is None:
            return
        try:
            from praisonaiagents.approval import ApprovalDecision

            decision = ApprovalDecision(
                approved=resolution.approved,
                reason=resolution.reason,
                approver="gateway",
            )
            coro = self._store.resolve(request_id, decision)
        except Exception:
            logger.exception(
                "Failed to build durable resolution for %s", request_id
            )
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Keep a strong reference until the task completes; the event loop
            # only holds a weak ref, so a discarded Task can be GC'd before the
            # audit-trail write runs (CPython asyncio docs warn about this).
            task = loop.create_task(coro)
            self._bg_tasks.add(task)
            task.add_done_callback(self._on_bg_task_done)
            return
        try:
            asyncio.run(coro)
        except Exception:
            logger.exception(
                "Failed to persist resolution for %s to durable store", request_id
            )

    def _on_bg_task_done(self, task: "asyncio.Task") -> None:
        """Drop the task ref and surface any error from the durable write."""
        self._bg_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Durable resolution write failed: %r", exc)

    # ── Explicit removal (for timeout cleanup) ────────────────────────

    def remove(self, request_id: str) -> bool:
        """Remove a pending request without resolving it. Returns ``True`` if found."""
        with self._lock:
            return self._pending.pop(request_id, None) is not None

    # ── Query API ─────────────────────────────────────────────────────

    def list_pending(self) -> List[Dict[str, Any]]:
        """List all pending requests as JSON-serialisable dicts."""
        with self._lock:
            self._prune()
            return [
                {
                    "request_id": r.request_id,
                    "tool_name": r.tool_name,
                    "arguments": r.arguments,
                    "agent_name": r.agent_name,
                    "risk_level": r.risk_level,
                    "created_at": r.created_at,
                    "age_seconds": round(time.time() - r.created_at, 1),
                }
                for r in self._pending.values()
            ]

    def get_pending(self, request_id: str) -> Optional[PendingRequest]:
        """Get a single pending request by ID."""
        with self._lock:
            self._prune()
            return self._pending.get(request_id)

    # ── Internal ──────────────────────────────────────────────────────

    def _make_id(self) -> str:
        """Generate a short human-readable request ID."""
        return f"apr-{secrets.token_hex(4)}"

    def _prune(self) -> None:
        """Remove expired pending requests (caller should hold lock)."""
        now = time.time()
        expired = [
            rid for rid, r in self._pending.items()
            if (now - r.created_at) >= self._ttl
        ]
        for rid in expired:
            req = self._pending.pop(rid)
            if req._future and not req._future.done() and req._loop:
                try:
                    req._loop.call_soon_threadsafe(
                        req._future.set_result,
                        Resolution(approved=False, reason="expired"),
                    )
                except RuntimeError:
                    pass  # loop already closed
            # Mark the durable row terminal so the audit trail records the
            # 'expired' state instead of leaving it 'pending' until the store's
            # own eviction TTL fires.
            self._record_expiry(rid)
            logger.debug("Expired approval request: %s", rid)

    def _record_expiry(self, request_id: str) -> None:
        """Best-effort mark of an expired approval in the durable store."""
        if self._store is None:
            return
        try:
            from praisonaiagents.approval import ApprovalDecision

            decision = ApprovalDecision(
                approved=False,
                reason="expired",
                approver="gateway",
                metadata={"terminal": "expired"},
            )
            coro = self._store.resolve(request_id, decision)
        except Exception:
            logger.debug("Could not build expiry decision for %s", request_id)
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            task = loop.create_task(coro)
            self._bg_tasks.add(task)
            task.add_done_callback(self._on_bg_task_done)
        else:
            try:
                asyncio.run(coro)
            except Exception:
                logger.debug("Failed to record expiry for %s", request_id)


# ── Durable store helpers ────────────────────────────────────────────

def _gateway_state_dir() -> Path:
    """Return the gateway state directory (mirrors the secure CLI path)."""
    import os

    base = os.environ.get("PRAISONAI_HOME")
    root = Path(base) if base else Path.home() / ".praisonai"
    return root / "state"


def _build_default_store() -> Optional["ApprovalStoreProtocol"]:
    """Build the default durable approval store, or ``None`` on failure.

    Reuses the wrapper's SQLite ``ApprovalStore`` at the standard state path
    so the gateway path shares durability semantics with the chat-native and
    secure CLI approval paths.
    """
    try:
        from praisonai.bots import ApprovalStore

        return ApprovalStore(path=_gateway_state_dir() / "approvals.sqlite")
    except Exception:
        logger.exception("Failed to build default durable approval store")
        return None


def _durable_enabled() -> bool:
    """Whether durable gateway approvals are opted in via env var."""
    import os

    val = os.environ.get("PRAISONAI_GATEWAY_DURABLE_APPROVALS", "").strip().lower()
    return val in ("1", "true", "yes", "on")


# ── Manager accessor (non-singleton) ─────────────────────────────────

# Default manager for CLI/backward compatibility
_default_manager: Optional[ExecApprovalManager] = None
_manager_lock = threading.Lock()


def get_default_exec_approval_manager(ttl: float = 300.0) -> ExecApprovalManager:
    """Get the default exec approval manager (for CLI and backward compatibility).

    When ``PRAISONAI_GATEWAY_DURABLE_APPROVALS`` is truthy the default manager
    is backed by a durable :class:`ApprovalStoreProtocol` store and a persisted
    allow-always list, so pending approvals and ``allow_always`` grants survive
    a gateway restart. Otherwise behaviour is unchanged (in-memory only).

    Args:
        ttl: Seconds before approval requests auto-expire (default 5 min).

    Returns:
        The default ExecApprovalManager instance.
    """
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                if _durable_enabled():
                    _default_manager = ExecApprovalManager(
                        ttl=ttl,
                        store=_build_default_store(),
                        allowlist_path=_gateway_state_dir() / "approval_allowlist.json",
                    )
                else:
                    _default_manager = ExecApprovalManager(ttl=ttl)
    return _default_manager


def get_exec_approval_manager(ttl: float = 300.0) -> ExecApprovalManager:
    """Backward compatibility alias for get_default_exec_approval_manager."""
    return get_default_exec_approval_manager(ttl)


def create_exec_approval_manager(
    ttl: float = 300.0,
    store: Optional["ApprovalStoreProtocol"] = None,
    allowlist_path: Optional[Union[str, Path]] = None,
) -> ExecApprovalManager:
    """Create a new exec approval manager instance (for per-agent use).

    Args:
        ttl: Seconds before approval requests auto-expire (default 5 min).
        store: Optional durable store implementing ``ApprovalStoreProtocol``.
        allowlist_path: Optional JSON file to persist allow-always grants.

    Returns:
        A new ExecApprovalManager instance.
    """
    return ExecApprovalManager(ttl=ttl, store=store, allowlist_path=allowlist_path)
