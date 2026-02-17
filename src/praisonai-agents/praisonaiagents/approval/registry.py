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
import logging
import os
from typing import Dict, List, Optional, Set

from .protocols import ApprovalDecision, ApprovalRequest

logger = logging.getLogger(__name__)

# Default dangerous tools — same as old approval.py
DEFAULT_DANGEROUS_TOOLS: Dict[str, str] = {
    "execute_command": "critical",
    "kill_process": "critical",
    "execute_code": "critical",
    "acp_execute_command": "critical",
    "write_file": "high",
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

    # ── Context helpers ──────────────────────────────────────────────────

    def mark_approved(self, tool_name: str) -> None:
        approved = self._approved_context.get(set())
        approved.add(tool_name)
        self._approved_context.set(approved)

    def is_already_approved(self, tool_name: str) -> bool:
        return tool_name in self._approved_context.get(set())

    def clear_approved(self) -> None:
        self._approved_context.set(set())

    def set_yaml_approved_tools(self, tools: List[str]) -> contextvars.Token:
        return self._yaml_approved_tools.set(set(tools))

    def reset_yaml_approved_tools(self, token: contextvars.Token) -> None:
        self._yaml_approved_tools.reset(token)

    def is_yaml_approved(self, tool_name: str) -> bool:
        try:
            return tool_name in self._yaml_approved_tools.get()
        except LookupError:
            return False

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
        if self.is_already_approved(tool_name):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        # Env auto-approve
        if self.is_env_auto_approve():
            self.mark_approved(tool_name)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        # YAML auto-approve
        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name)
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
            # Fallback: run async method
            try:
                decision = asyncio.run(backend.request_approval(request))
            except RuntimeError:
                # Already in an event loop — fall back to thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, backend.request_approval(request))
                    decision = future.result(timeout=self.timeout)

        if decision.approved:
            self.mark_approved(tool_name)
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

        if self.is_already_approved(tool_name):
            return ApprovalDecision(approved=True, reason="Already approved in context")

        if self.is_env_auto_approve():
            self.mark_approved(tool_name)
            return ApprovalDecision(approved=True, reason="Auto-approved (env)", approver="env")

        if self.is_yaml_approved(tool_name):
            self.mark_approved(tool_name)
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
            self.mark_approved(tool_name)
        return decision
