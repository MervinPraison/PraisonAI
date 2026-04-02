"""
Async approval-request queue for the PraisonAI gateway.

Manages pending approval requests, resolution, and an optional allow-always
permission list so users don't have to re-approve the same tool repeatedly.

This is a *heavy implementation* and lives in the wrapper, not the core SDK.
The core SDK only provides :class:`ApprovalProtocol` in
``praisonaiagents.approval.protocols``.
"""

from __future__ import annotations

import asyncio
import logging
import time
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


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


# ── Permission allow-list ────────────────────────────────────────────

class PermissionAllowlist:
    """Thread-safe set of tool names that are permanently allowed.

    When a user resolves a request with ``allow_always=True``, the tool
    is added here so future calls skip approval.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._allowed: Set[str] = set()

    def add(self, tool_name: str) -> None:
        with self._lock:
            self._allowed.add(tool_name)

    def remove(self, tool_name: str) -> bool:
        with self._lock:
            try:
                self._allowed.remove(tool_name)
                return True
            except KeyError:
                return False

    def __contains__(self, tool_name: str) -> bool:
        with self._lock:
            return tool_name in self._allowed

    def list(self) -> List[str]:
        with self._lock:
            return sorted(self._allowed)


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

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()  # threading.Lock for cross-thread safety
        self._pending: Dict[str, PendingRequest] = {}
        self.allowlist = PermissionAllowlist()

    # ── Registration ──────────────────────────────────────────────────

    async def register(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_name: str = "",
        risk_level: str = "medium",
    ) -> tuple:
        """Create a pending request and return ``(request_id, future)``.

        If the tool is in the :attr:`allowlist`, the future is resolved
        immediately with ``approved=True``.
        """
        # Fast path: already permanently allowed
        if tool_name in self.allowlist:
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
            self.allowlist.add(req.tool_name)
            logger.info("Tool '%s' added to allow-always list", req.tool_name)

        if req._future and not req._future.done() and req._loop:
            req._loop.call_soon_threadsafe(
                req._future.set_result, resolution,
            )

        logger.info(
            "Approval resolved: %s -> %s",
            request_id,
            "approved" if resolution.approved else "denied",
        )
        return True

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
            logger.debug("Expired approval request: %s", rid)


# ── Module-level singleton accessor ──────────────────────────────────

_global_manager: Optional[ExecApprovalManager] = None
_manager_lock = threading.Lock()


def get_exec_approval_manager(ttl: float = 300.0) -> ExecApprovalManager:
    """Get or create the global :class:`ExecApprovalManager` singleton."""
    global _global_manager
    if _global_manager is None:
        with _manager_lock:
            if _global_manager is None:
                _global_manager = ExecApprovalManager(ttl=ttl)
    return _global_manager
