"""
Approval registry for PraisonAI Agents.

Centralises approval state that was previously scattered across module-level
globals.  Supports **per-agent** backends so different agents can use
different approval channels (console, webhook, Slack, …) without touching
the ``Agent`` class.

Usage (no Agent param needed)::

    from praisonaiagents.approval import get_approval_registry, AutoApproveBackend

    registry = get_approval_registry()
    registry.set_backend(AutoApproveBackend(), agent_name="bot-agent")
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
from praisonaiagents._logging import get_logger
import os
from typing import Dict, List, Optional, Set

from .protocols import ApprovalDecision, ApprovalRequest

logger = get_logger(__name__)

# Default dangerous tools — same as old approval.py
DEFAULT_DANGEROUS_TOOLS: Dict[str, str] = {
    "execute_command": "critical",
    "kill_process": "critical",
    "execute_code": "critical",
    "acp_execute_command": "critical",
    "write_file": "high",
    "edit_file": "high",
    "apply_patch": "high",
    "delete_file": "high",
    "move_file": "high",
    "copy_file": "high",
    "acp_create_file": "high",
    "acp_edit_file": "high",
    "acp_delete_file": "high",
    "execute_query": "high",
    "evaluate": "medium",
    "crawl": "medium",
    "scrape_page": "medium",
}

# Permission presets — resolved to deny frozensets at Agent.__init__ time.
# Usage: Agent(approval="safe") — or set PRAISONAI_TOOL_SAFETY=<preset>
# which applies as the default when no ``approval=`` kwarg is passed.
#
# ``default`` is the baseline we apply when nothing is configured: it
# only blocks operations the LLM should never execute unattended —
# destructive file ops (delete/move/copy) and arbitrary shell/code
# execution. Read, create and edit stay allowed because those are
# what 99% of useful agent workflows need. Users who want the old
# ``trust the LLM with everything`` behaviour pass ``approval="full"``
# or set ``PRAISONAI_TOOL_SAFETY=off``; users who want stricter
# controls can opt into ``approval="safe"`` or ``"read_only"``.
PERMISSION_PRESETS = {
    # "default" — blocks delete + shell/code exec. Allows read/create/edit.
    "default": frozenset({
        "execute_command", "kill_process", "execute_code", "acp_execute_command",
        "delete_file", "move_file", "copy_file", "acp_delete_file",
    }),
    # "safe" — blocks all dangerous tools (file writes, shell exec, etc.)
    "safe": frozenset(DEFAULT_DANGEROUS_TOOLS.keys()),
    # "read_only" — alias of "safe" (blocks all dangerous tools)
    "read_only": frozenset(DEFAULT_DANGEROUS_TOOLS.keys()),
    # "full" — no restrictions (trust the LLM). Equivalent to "off" env.
    "full": frozenset(),
    # "off" — alias of "full" for the env-var off-switch.
    "off": frozenset(),
}

class ApprovalRegistry:
    """Per-agent approval configuration.

    Replaces the old global mutable sets/dicts while keeping the same
    semantics.  The singleton instance is obtained via
    :func:`get_approval_registry`.
    """

    def __init__(self) -> None:
        # Backends
        self._global_backend = None  # type: ignore[assignment]
        self._agent_backends: Dict[str, object] = {}

        # Tool requirements (mirrors old APPROVAL_REQUIRED_TOOLS / TOOL_RISK_LEVELS)
        self._required_tools: Set[str] = set()
        self._risk_levels: Dict[str, str] = {}

        # Per-agent, per-tool auto-approval (G-A fix)
        self._agent_tool_auto_approve: Dict[tuple[str, str], bool] = {}

        # In-memory "this session" scoped approvals: (agent_name, target) grants
        # that live only for the current process (never written to disk), keyed
        # by the reusable permission target so they cover matching calls for the
        # rest of the run. Cleared by ``clear_approved``.
        self._session_scoped_targets: Set[tuple[Optional[str], str]] = set()

        # Context variables (per-coroutine / per-thread)
        self._approved_context: contextvars.ContextVar[Set[str]] = contextvars.ContextVar(
            "approved_context", default=set()
        )
        self._yaml_approved_tools: contextvars.ContextVar[Set[str]] = contextvars.ContextVar(
            "yaml_approved_tools", default=set()
        )

        # Timeout for async approval calls
        self.timeout: float = 300.0

        # Initialise with dangerous-tool defaults
        for tool_name, risk in DEFAULT_DANGEROUS_TOOLS.items():
            self._required_tools.add(tool_name)
            self._risk_levels[tool_name] = risk

    # ── Backend management ───────────────────────────────────────────────

    def set_backend(self, backend: object, agent_name: Optional[str] = None) -> None:
        """Set the approval backend globally or for a specific agent.

        Args:
            backend:    Any object satisfying :class:`ApprovalProtocol`.
            agent_name: If provided, apply only to this agent.
        """
        if agent_name:
            self._agent_backends[agent_name] = backend
        else:
            self._global_backend = backend

    def remove_backend(self, agent_name: Optional[str] = None) -> None:
        """Remove a previously set backend."""
        if agent_name:
            self._agent_backends.pop(agent_name, None)
        else:
            self._global_backend = None

    def get_backend(self, agent_name: Optional[str] = None) -> object:
        """Resolve the backend for *agent_name* (falls back to global, then console)."""
        if agent_name and agent_name in self._agent_backends:
            return self._agent_backends[agent_name]
        if self._global_backend is not None:
            return self._global_backend
        # Lazy import to avoid circular / heavy import at module level
        from .backends import ConsoleBackend
        return ConsoleBackend()

    # ── Tool requirement management ──────────────────────────────────────

    def add_requirement(self, tool_name: str, risk_level: str = "high") -> None:
        self._required_tools.add(tool_name)
        self._risk_levels[tool_name] = risk_level

    def remove_requirement(self, tool_name: str) -> None:
        self._required_tools.discard(tool_name)
        self._risk_levels.pop(tool_name, None)

    def is_required(self, tool_name: str) -> bool:
        return tool_name in self._required_tools

    def get_risk_level(self, tool_name: str) -> Optional[str]:
        return self._risk_levels.get(tool_name)

    # ── Per-tool auto-approval (G-A fix) ─────────────────────────────────

    def auto_approve_tool(self, tool_name: str, agent_name: str) -> None:
        """Pre-approve a single tool for a specific agent."""
        if not agent_name:
            raise ValueError("Skill auto-approval requires a stable agent/session scope")
        self._agent_tool_auto_approve[(agent_name, tool_name)] = True

    def is_auto_approved(self, tool_name: str, agent_name: str) -> bool:
        """Check if a tool is auto-approved for a specific agent."""
        if not agent_name:
            return False
        return self._agent_tool_auto_approve.get((agent_name, tool_name), False)

    # ── Context helpers ──────────────────────────────────────────────────

    @staticmethod
    def _approval_cache_key(tool_name: str, arguments: Dict) -> str:
        payload = json.dumps(arguments or {}, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{tool_name}:{digest}"

    def mark_approved(self, tool_name: str, arguments: Optional[Dict] = None) -> None:
        approved = self._approved_context.get(set())
        approved.add(self._approval_cache_key(tool_name, arguments or {}))
        self._approved_context.set(approved)

    def is_already_approved(self, tool_name: str, arguments: Optional[Dict] = None) -> bool:
        # Honour an explicit mark_approved() from the agent approval path even
        # for critical tools (e.g. execute_command after AutoApproveBackend).
        if self._approval_cache_key(tool_name, arguments or {}) in self._approved_context.get(set()):
            return True
        return False

    def _is_session_scoped(
        self, agent_name: Optional[str], tool_name: str, arguments: Optional[Dict]
    ) -> bool:
        """Return True if a "this session" grant covers this call for the run.

        Checks the in-memory session store by the reusable permission target so
        a single ``session`` approval covers matching calls (e.g. the same
        ``bash:git status *`` prefix) without persisting anything to disk.
        """
        if not self._session_scoped_targets:
            return False
        try:
            from .utils import build_permission_target

            target = build_permission_target(tool_name, arguments)
        except Exception:  # noqa: BLE001 — never block on target derivation
            return False
        return (agent_name, target) in self._session_scoped_targets

    def _persist_scoped_decision(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Optional[Dict],
        decision: ApprovalDecision,
    ) -> None:
        """Record a ``session``/``always`` decision for reuse this run (or beyond).

        * ``always`` decisions are routed into :class:`PermissionManager` (which
          writes to ``approvals.json``) so future runs short-circuit too.
        * ``session`` decisions are recorded **only** in the in-memory
          ``_session_scoped_targets`` store — never on disk — so they cover
          matching calls for the rest of *this* run and then vanish. Persisting
          them via ``PermissionManager`` would reload them next run and violate
          the "this session only" contract shown in the prompt.

        A missing ``agent_name`` is skipped for the durable ``always`` path: an
        approval stored without an agent boundary matches *any* later agent
        making the same target call, so a nameless grant is not persisted where
        it could cross agent boundaries (it still gets the in-memory fast-path).

        Any failure is swallowed — the in-memory fast-path still applies, so a
        persistence hiccup never blocks execution.
        """
        scope = getattr(decision, "scope", "once")
        if scope not in ("session", "always"):
            return
        if not decision.approved:
            return

        if scope == "session":
            try:
                from .utils import build_permission_target

                target = build_permission_target(tool_name, arguments)
                self._session_scoped_targets.add((agent_name, target))
            except Exception as e:  # noqa: BLE001 — best-effort, in-memory only
                logger.debug(
                    "Could not record session approval for tool '%s': %s",
                    tool_name, e,
                )
            return

        # scope == "always" — persist to the durable store.
        if not agent_name:
            logger.debug(
                "Skipping persistent 'always' approval for tool '%s': no agent "
                "name (would match any agent). Kept in-memory for this run.",
                tool_name,
            )
            # Fall back to session semantics so the grant still helps this run.
            try:
                from .utils import build_permission_target

                self._session_scoped_targets.add(
                    (agent_name, build_permission_target(tool_name, arguments))
                )
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            from ..permissions import PermissionManager
            from .utils import build_permission_target

            target = build_permission_target(tool_name, arguments)
            manager = PermissionManager(agent_name=agent_name)
            manager.approve(
                target,
                decision.approved,
                scope=scope,
                agent_name=agent_name,
                reusable_scope=True,
                pattern=getattr(decision, "scope_pattern", None),
            )
        except Exception as e:  # noqa: BLE001 — persistence is best-effort
            logger.warning(
                "Could not persist %s approval for tool '%s': %s", scope, tool_name, e
            )

    def clear_approved(self) -> None:
        self._approved_context.set(set())
        self._session_scoped_targets.clear()

    def set_yaml_approved_tools(self, tools: List[str]) -> contextvars.Token:
        return self._yaml_approved_tools.set(set(tools))

    def add_yaml_approved_tools(self, tools: List[str]) -> contextvars.Token:
        """Merge ``tools`` into the YAML-approved set without clobbering it.

        Unlike :meth:`set_yaml_approved_tools`, this preserves any tools already
        approved in the current context. Returns a token that can be passed to
        :meth:`reset_yaml_approved_tools` to restore the prior approval set.
        """
        try:
            current = set(self._yaml_approved_tools.get())
        except LookupError:
            current = set()
        return self._yaml_approved_tools.set(current | set(tools))

    def reset_yaml_approved_tools(self, token: contextvars.Token) -> None:
        self._yaml_approved_tools.reset(token)

    def is_yaml_approved(self, tool_name: str) -> bool:
        try:
            if tool_name not in self._yaml_approved_tools.get():
                return False
        except LookupError:
            return False
        if self.get_risk_level(tool_name) == "critical":
            return False
        return True

    # ── Env-var check ────────────────────────────────────────────────────

    @staticmethod
    def is_env_auto_approve() -> bool:
        return os.environ.get("PRAISONAI_AUTO_APPROVE", "").lower() in ("true", "1", "yes")

    # ── Approval entry points ────────────────────────────────────────────

    def approve_sync(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Dict,
    ) -> ApprovalDecision:
        """Synchronous approval — used by ``Agent._execute_tool_impl``."""
        # Fast-path: not required
        if not self.is_required(tool_name):
            return ApprovalDecision(approved=True, reason="No approval required")

        # Already approved in this context
        if self.is_already_approved(tool_name, arguments):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        # "This session" scoped grant covers matching calls for the run
        if self._is_session_scoped(agent_name, tool_name, arguments):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Approved (session)", approver="session")

        # Check per-tool auto-approval (G-A fix)
        if self.is_auto_approved(tool_name, agent_name):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (skill)", approver="skill")

        # Env auto-approve
        if self.is_env_auto_approve():
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        # YAML auto-approve
        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (yaml)", approver="yaml")

        # Delegate to backend
        backend = self.get_backend(agent_name)
        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            risk_level=self._risk_levels.get(tool_name, "medium"),
            agent_name=agent_name,
        )

        # Prefer sync method if available
        if hasattr(backend, "request_approval_sync"):
            decision = backend.request_approval_sync(request)
        else:
            # Use shared utility for consistent async-to-sync bridging
            from .utils import run_coroutine_safely
            decision = run_coroutine_safely(
                backend.request_approval(request),
                timeout=self.timeout
            )

        if decision.approved:
            self.mark_approved(tool_name, arguments)
        self._persist_scoped_decision(agent_name, tool_name, arguments, decision)
        return decision

    async def approve_async(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Dict,
    ) -> ApprovalDecision:
        """Asynchronous approval — used by async tool execution path."""
        # Fast-path: not required
        if not self.is_required(tool_name):
            return ApprovalDecision(approved=True, reason="No approval required")

        if self.is_already_approved(tool_name, arguments):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        # "This session" scoped grant covers matching calls for the run
        if self._is_session_scoped(agent_name, tool_name, arguments):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Approved (session)", approver="session")

        # Check per-tool auto-approval (G-A fix)
        if self.is_auto_approved(tool_name, agent_name):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (skill)", approver="skill")

        if self.is_env_auto_approve():
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name, arguments)
            return ApprovalDecision(approved=True, reason="Auto-approved (yaml)", approver="yaml")

        backend = self.get_backend(agent_name)
        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            risk_level=self._risk_levels.get(tool_name, "medium"),
            agent_name=agent_name,
        )

        try:
            decision = await asyncio.wait_for(
                backend.request_approval(request),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            decision = ApprovalDecision(approved=False, reason="Approval timed out")

        if decision.approved:
            self.mark_approved(tool_name, arguments)
        self._persist_scoped_decision(agent_name, tool_name, arguments, decision)
        return decision
