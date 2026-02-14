"""
Extensible Approval Protocol for PraisonAI Agents.

This package provides a protocol-driven, per-agent approval system for
tool executions.  It is fully backward-compatible with the old
``approval.py`` module — all existing imports continue to work.

Quick start (no Agent class changes needed)::

    from praisonaiagents.approval import get_approval_registry, AutoApproveBackend

    # Global auto-approve for all agents
    get_approval_registry().set_backend(AutoApproveBackend())

    # Per-agent backend
    get_approval_registry().set_backend(AutoApproveBackend(), agent_name="bot")

Custom backend::

    from praisonaiagents.approval import ApprovalProtocol, ApprovalRequest, ApprovalDecision

    class WebhookBackend:
        async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
            # POST to external service, wait for response
            return ApprovalDecision(approved=True)

    get_approval_registry().set_backend(WebhookBackend())
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Dict, List, Literal, Optional, Set

# ── New protocol-driven exports ──────────────────────────────────────────────

from .protocols import ApprovalProtocol, ApprovalRequest  # noqa: F401
from .protocols import ApprovalDecision  # noqa: F401
from .backends import AutoApproveBackend, ConsoleBackend, CallbackBackend, AgentApproval  # noqa: F401
from .registry import ApprovalRegistry, DEFAULT_DANGEROUS_TOOLS  # noqa: F401

logger = logging.getLogger(__name__)

# ── Singleton registry ───────────────────────────────────────────────────────

_registry: Optional[ApprovalRegistry] = None


def get_approval_registry() -> ApprovalRegistry:
    """Return the global singleton :class:`ApprovalRegistry`."""
    global _registry
    if _registry is None:
        _registry = ApprovalRegistry()
    return _registry


# ── Backward-compatible API (delegates to registry) ─────────────────────────

# These globals are kept for code that imports them directly.
APPROVAL_REQUIRED_TOOLS: Set[str] = get_approval_registry()._required_tools
TOOL_RISK_LEVELS: Dict[str, str] = get_approval_registry()._risk_levels

# Legacy global callback holder — set_approval_callback wraps it into a backend
approval_callback: Optional[Callable] = None


def set_approval_callback(callback_fn: Optional[Callable]) -> None:
    """Set a custom approval callback (legacy API).

    The callback is wrapped into a :class:`CallbackBackend` and set as the
    global backend on the registry.
    """
    global approval_callback
    approval_callback = callback_fn
    reg = get_approval_registry()
    if callback_fn is not None:
        reg.set_backend(CallbackBackend(callback_fn))
    else:
        reg.remove_backend()


def get_approval_callback() -> Optional[Callable]:
    """Get the current approval callback function (legacy API)."""
    return approval_callback


def mark_approved(tool_name: str) -> None:
    get_approval_registry().mark_approved(tool_name)


def is_already_approved(tool_name: str) -> bool:
    return get_approval_registry().is_already_approved(tool_name)


def is_yaml_approved(tool_name: str) -> bool:
    return get_approval_registry().is_yaml_approved(tool_name)


def is_env_auto_approve() -> bool:
    return ApprovalRegistry.is_env_auto_approve()


def set_yaml_approved_tools(tools: List[str]) -> contextvars.Token:
    return get_approval_registry().set_yaml_approved_tools(tools)


def reset_yaml_approved_tools(token: contextvars.Token) -> None:
    get_approval_registry().reset_yaml_approved_tools(token)


def clear_approval_context() -> None:
    get_approval_registry().clear_approved()


def configure_default_approvals() -> None:
    """Re-configure default dangerous tools (idempotent)."""
    reg = get_approval_registry()
    for tool_name, risk_level in DEFAULT_DANGEROUS_TOOLS.items():
        reg.add_requirement(tool_name, risk_level)


def add_approval_requirement(tool_name: str, risk_level: str = "high") -> None:
    get_approval_registry().add_requirement(tool_name, risk_level)
    APPROVAL_REQUIRED_TOOLS.add(tool_name)
    TOOL_RISK_LEVELS[tool_name] = risk_level


def remove_approval_requirement(tool_name: str) -> None:
    get_approval_registry().remove_requirement(tool_name)
    APPROVAL_REQUIRED_TOOLS.discard(tool_name)
    TOOL_RISK_LEVELS.pop(tool_name, None)


def is_approval_required(tool_name: str) -> bool:
    return get_approval_registry().is_required(tool_name)


def get_risk_level(tool_name: str) -> Optional[str]:
    return get_approval_registry().get_risk_level(tool_name)


# ── Legacy console callback (kept for direct callers) ───────────────────────

def console_approval_callback(function_name: str, arguments: Dict, risk_level: str) -> ApprovalDecision:
    """Default console-based approval callback (legacy API)."""
    backend = ConsoleBackend()
    request = ApprovalRequest(
        tool_name=function_name,
        arguments=arguments,
        risk_level=risk_level,
    )
    return backend.request_approval_sync(request)


# ── Legacy async request_approval ────────────────────────────────────────────

async def request_approval(function_name: str, arguments: Dict) -> ApprovalDecision:
    """Request approval for a tool execution (legacy async API)."""
    return await get_approval_registry().approve_async(None, function_name, arguments)


# ── require_approval decorator (unchanged semantics) ─────────────────────────

RiskLevel = Literal["critical", "high", "medium", "low"]


def require_approval(risk_level: RiskLevel = "high"):
    """Decorator to mark a tool as requiring human approval."""
    def decorator(func):
        tool_name = getattr(func, '__name__', str(func))
        reg = get_approval_registry()
        reg.add_requirement(tool_name, risk_level)
        APPROVAL_REQUIRED_TOOLS.add(tool_name)
        TOOL_RISK_LEVELS[tool_name] = risk_level

        @wraps(func)
        def wrapper(*args, **kwargs):
            if is_already_approved(tool_name):
                return func(*args, **kwargs)
            if is_yaml_approved(tool_name):
                mark_approved(tool_name)
                return func(*args, **kwargs)
            if is_env_auto_approve():
                mark_approved(tool_name)
                return func(*args, **kwargs)
            try:
                try:
                    asyncio.get_running_loop()
                    raise RuntimeError("Use sync fallback in async context")
                except RuntimeError:
                    decision = asyncio.run(request_approval(tool_name, kwargs))
            except Exception as e:
                logging.warning(f"Async approval failed, using sync fallback: {e}")
                decision = console_approval_callback(tool_name, kwargs, risk_level)
            if not decision.approved:
                raise PermissionError(f"Execution of {tool_name} denied: {decision.reason}")
            mark_approved(tool_name)
            kwargs.update(decision.modified_args)
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if is_already_approved(tool_name):
                return await func(*args, **kwargs)
            if is_yaml_approved(tool_name):
                mark_approved(tool_name)
                return await func(*args, **kwargs)
            if is_env_auto_approve():
                mark_approved(tool_name)
                return await func(*args, **kwargs)
            decision = await request_approval(tool_name, kwargs)
            if not decision.approved:
                raise PermissionError(f"Execution of {tool_name} denied: {decision.reason}")
            mark_approved(tool_name)
            kwargs.update(decision.modified_args)
            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


# ── PermissionAllowlist (kept as-is) ─────────────────────────────────────────


@dataclass
class ToolPermission:
    """Permission entry for a tool."""
    tool_name: str
    allowed_paths: List[str] = field(default_factory=list)
    session_only: bool = False


class PermissionAllowlist:
    """Persistent permission allowlist for tools."""

    def __init__(self):
        self._tools: Dict[str, ToolPermission] = {}
        self._session_tools: Set[str] = set()

    def add_tool(self, tool_name: str, paths: Optional[List[str]] = None, session_only: bool = False) -> None:
        self._tools[tool_name] = ToolPermission(tool_name=tool_name, allowed_paths=paths or [], session_only=session_only)
        if session_only:
            self._session_tools.add(tool_name)

    def remove_tool(self, tool_name: str) -> bool:
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._session_tools.discard(tool_name)
            return True
        return False

    def is_allowed(self, tool_name: str, path: Optional[str] = None) -> bool:
        if tool_name not in self._tools:
            return False
        permission = self._tools[tool_name]
        if not permission.allowed_paths:
            return True
        if path is None:
            return True
        for allowed_path in permission.allowed_paths:
            norm_allowed = os.path.normpath(allowed_path)
            norm_path = os.path.normpath(path)
            if norm_path.startswith(norm_allowed):
                return True
        return False

    def is_empty(self) -> bool:
        return len(self._tools) == 0

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def clear_session_permissions(self) -> None:
        for tool_name in list(self._session_tools):
            if tool_name in self._tools:
                del self._tools[tool_name]
        self._session_tools.clear()

    def save(self, filepath: str) -> None:
        data = {
            "tools": {
                name: {"allowed_paths": perm.allowed_paths, "session_only": perm.session_only}
                for name, perm in self._tools.items()
                if not perm.session_only
            }
        }
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "PermissionAllowlist":
        allowlist = cls()
        if not os.path.exists(filepath):
            return allowlist
        with open(filepath, "r") as f:
            data = json.load(f)
        for tool_name, tool_data in data.get("tools", {}).items():
            allowlist.add_tool(tool_name, paths=tool_data.get("allowed_paths", []), session_only=tool_data.get("session_only", False))
        return allowlist


_permission_allowlist: Optional[PermissionAllowlist] = None


def get_permission_allowlist() -> PermissionAllowlist:
    global _permission_allowlist
    if _permission_allowlist is None:
        _permission_allowlist = PermissionAllowlist()
    return _permission_allowlist


def set_permission_allowlist(allowlist: PermissionAllowlist) -> None:
    global _permission_allowlist
    _permission_allowlist = allowlist
