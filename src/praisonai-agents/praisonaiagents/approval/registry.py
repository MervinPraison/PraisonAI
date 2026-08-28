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

# Internal, namespaced synthetic approval target for the runaway-safety gate.
# A detected doom/repeat loop routes through the approval pipeline as this
# target instead of unconditionally blocking. The double-underscore name can
# never collide with a real agent tool (tool names are identifiers the model
# emits), so registering it does NOT force approval onto — or block — an
# ordinary user tool, and it is intentionally kept OUT of
# ``DEFAULT_DANGEROUS_TOOLS`` so the ``safe``/``read_only`` presets are
# unaffected. It is registered at ``critical`` risk (see ``__init__``) so the
# default posture (no explicit allow) still stops, preserving the historical
# hard-block; an explicit allow (``__doom_loop__``/``doom_loop`` policy,
# env/YAML auto-approve, or a human continue) lets a legitimate repeat
# (e.g. polling a build status) proceed.
DOOM_LOOP_TARGET = "__doom_loop__"

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

        # Tool requirements (mirrors old APPROVAL_REQUIRED_TOOLS / TOOL_RISK_LEVELS).
        # These hold process-wide defaults (e.g. DEFAULT_DANGEROUS_TOOLS and any
        # intentional global registration).
        self._required_tools: Set[str] = set()
        self._risk_levels: Dict[str, str] = {}

        # Per-agent tool requirements. A PermissionManager ``ask`` rule belongs
        # to a single agent, so it must not leak an approval gate onto unrelated
        # agents sharing the same process. Mirrors the agent-keyed pattern used
        # by ``_agent_backends`` / ``_agent_tool_auto_approve``.
        self._agent_required_tools: Dict[str, Set[str]] = {}
        self._agent_risk_levels: Dict[tuple[str, str], str] = {}

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

        # Register the internal runaway-safety gate at ``critical`` risk so a
        # detected doom-loop stops by default (backward compatible) while still
        # routing through the approval pipeline. Kept separate from the public
        # dangerous-tool set so it can never gate a real user tool.
        self._required_tools.add(DOOM_LOOP_TARGET)
        self._risk_levels[DOOM_LOOP_TARGET] = "critical"

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

    def add_requirement(
        self,
        tool_name: str,
        risk_level: str = "high",
        agent_name: Optional[str] = None,
    ) -> None:
        """Mark *tool_name* as requiring approval.

        When *agent_name* is given the requirement is scoped to that agent only
        (used for per-agent ``PermissionManager`` ``ask`` rules), so it never
        forces approval onto other agents in the same process. Omitting
        *agent_name* keeps the historical process-wide behaviour used for
        genuinely dangerous tools registered at startup.
        """
        if agent_name:
            self._agent_required_tools.setdefault(agent_name, set()).add(tool_name)
            self._agent_risk_levels[(agent_name, tool_name)] = risk_level
        else:
            self._required_tools.add(tool_name)
            self._risk_levels[tool_name] = risk_level

    def remove_requirement(
        self, tool_name: str, agent_name: Optional[str] = None
    ) -> None:
        if agent_name:
            tools = self._agent_required_tools.get(agent_name)
            if tools is not None:
                tools.discard(tool_name)
            self._agent_risk_levels.pop((agent_name, tool_name), None)
        else:
            self._required_tools.discard(tool_name)
            self._risk_levels.pop(tool_name, None)

    def is_required(self, tool_name: str, agent_name: Optional[str] = None) -> bool:
        if agent_name and tool_name in self._agent_required_tools.get(agent_name, ()):
            return True
        return tool_name in self._required_tools

    def get_risk_level(
        self, tool_name: str, agent_name: Optional[str] = None
    ) -> Optional[str]:
        if agent_name:
            level = self._agent_risk_levels.get((agent_name, tool_name))
            if level is not None:
                return level
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
    def _approval_cache_key(
        tool_name: str,
        arguments: Dict,
        agent_name: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> str:
        # Scope the key to the requesting agent so one agent's approval never
        # silently pre-authorizes an identical call from a different, stricter
        # agent in the same context. Prefer the per-instance ``scope_id`` (e.g.
        # ``Agent._approval_scope_id``) when supplied: the display ``agent_name``
        # defaults to ``"Agent"`` for every unnamed agent, so keying the
        # context cache by name alone lets two same-named instances sharing an
        # execution context pre-authorize each other before the per-instance
        # session lookup runs. Falls back to ``agent_name`` for backward compat.
        # ``*`` is the sentinel for calls made outside any Agent (e.g. bare
        # module-level tool calls).
        from .utils import hash_tool_args
        scope = scope_id or agent_name or '*'
        return f"{scope}:{tool_name}:{hash_tool_args(arguments)}"

    def mark_approved(
        self,
        tool_name: str,
        arguments: Optional[Dict] = None,
        agent_name: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> None:
        approved = self._approved_context.get(set())
        approved.add(self._approval_cache_key(tool_name, arguments or {}, agent_name, scope_id))
        self._approved_context.set(approved)

    def is_already_approved(
        self,
        tool_name: str,
        arguments: Optional[Dict] = None,
        agent_name: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> bool:
        # Honour an explicit mark_approved() from the agent approval path even
        # for critical tools (e.g. execute_command after AutoApproveBackend).
        if self._approval_cache_key(tool_name, arguments or {}, agent_name, scope_id) in self._approved_context.get(set()):
            return True
        return False

    def _is_session_scoped(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Optional[Dict],
        scope_id: Optional[str] = None,
    ) -> bool:
        """Return True if a "this session" grant covers this call for the run.

        Checks the in-memory session store by the reusable permission target so
        a single ``session`` approval covers matching calls (e.g. the same
        ``bash:git status *`` prefix) without persisting anything to disk.

        ``scope_id`` is a per-Agent-instance key (e.g. ``Agent._approval_scope_id``).
        When provided it is used as the store key instead of the display name so
        two same-named agents (every unnamed ``Agent()`` defaults to ``"Agent"``)
        can't inherit each other's human-granted session approval. Falls back to
        ``agent_name`` for backward compatibility when no id is supplied.
        """
        if not self._session_scoped_targets:
            return False
        try:
            from .utils import build_permission_target

            target = build_permission_target(tool_name, arguments)
        except Exception:  # noqa: BLE001 — never block on target derivation
            return False
        key = scope_id if scope_id is not None else agent_name
        return (key, target) in self._session_scoped_targets

    def _persist_scoped_decision(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Optional[Dict],
        decision: ApprovalDecision,
        scope_id: Optional[str] = None,
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

        # In-memory "this session" grants are keyed per Agent instance
        # (scope_id) when available, so a session approval granted on one worker
        # cannot silently unlock the same tool for a distinct same-named worker.
        session_key = scope_id if scope_id is not None else agent_name

        if scope == "session":
            try:
                from .utils import build_permission_target

                target = build_permission_target(tool_name, arguments)
                self._session_scoped_targets.add((session_key, target))
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
                    (session_key, build_permission_target(tool_name, arguments))
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
        force: bool = False,
        auto_approve_scope: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> ApprovalDecision:
        """Synchronous approval — used by ``Agent._execute_tool_impl``.

        ``force`` gates this single call even when the tool is not otherwise
        registered as requiring approval (e.g. a per-agent ``PermissionManager``
        ``ask`` rule). It applies only to this call and never mutates shared
        registry state, so it cannot leak an approval gate onto other agents.

        ``auto_approve_scope`` is the unique per-instance key used *only* for
        the skill auto-approval check. It defaults to ``agent_name`` so callers
        that don't pass it keep the old behaviour; passing a per-instance id
        (e.g. ``Agent._approval_scope_id``) prevents skill grants from leaking
        across unrelated agents that share the same display name.

        ``scope_id`` is the same per-instance key applied to the in-memory
        "this session" grant store, so a human "[s] this session" approval on
        one agent can't silently unlock the tool for a distinct same-named
        agent. ``agent_name`` is still used for name-keyed lookups (per-agent
        backend, risk level, ``ask`` rules, durable ``always`` persistence).
        """
        auto_scope = auto_approve_scope or agent_name
        # Fast-path: not required (checks both global and this agent's scope)
        if not force and not self.is_required(tool_name, agent_name):
            return ApprovalDecision(approved=True, reason="No approval required")

        # Already approved in this context
        if self.is_already_approved(tool_name, arguments, agent_name, scope_id):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        # "This session" scoped grant covers matching calls for the run
        if self._is_session_scoped(agent_name, tool_name, arguments, scope_id):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Approved (session)", approver="session")

        # Check per-tool auto-approval (G-A fix)
        if self.is_auto_approved(tool_name, auto_scope):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (skill)", approver="skill")

        # Env auto-approve
        if self.is_env_auto_approve():
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        # YAML auto-approve
        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (yaml)", approver="yaml")

        # Delegate to backend
        backend = self.get_backend(agent_name)
        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            risk_level=self.get_risk_level(tool_name, agent_name) or "medium",
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
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
        self._persist_scoped_decision(agent_name, tool_name, arguments, decision, scope_id)
        return decision

    async def approve_async(
        self,
        agent_name: Optional[str],
        tool_name: str,
        arguments: Dict,
        force: bool = False,
        auto_approve_scope: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> ApprovalDecision:
        """Asynchronous approval — used by async tool execution path.

        See :meth:`approve_sync` for the ``force``, ``auto_approve_scope`` and
        ``scope_id`` semantics (per-call gate, no shared-state mutation,
        per-instance session-grant keying).
        """
        auto_scope = auto_approve_scope or agent_name
        # Fast-path: not required (checks both global and this agent's scope)
        if not force and not self.is_required(tool_name, agent_name):
            return ApprovalDecision(approved=True, reason="No approval required")

        if self.is_already_approved(tool_name, arguments, agent_name, scope_id):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        # "This session" scoped grant covers matching calls for the run
        if self._is_session_scoped(agent_name, tool_name, arguments, scope_id):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Approved (session)", approver="session")

        # Check per-tool auto-approval (G-A fix)
        if self.is_auto_approved(tool_name, auto_scope):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (skill)", approver="skill")

        if self.is_env_auto_approve():
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
            return ApprovalDecision(approved=True, reason="Auto-approved (yaml)", approver="yaml")

        backend = self.get_backend(agent_name)
        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            risk_level=self.get_risk_level(tool_name, agent_name) or "medium",
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
            self.mark_approved(tool_name, arguments, agent_name, scope_id)
        self._persist_scoped_decision(agent_name, tool_name, arguments, decision, scope_id)
        return decision
