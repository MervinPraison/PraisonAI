"""
Approval protocol definitions for PraisonAI Agents.

Defines the structural contract for approval backends via typing.Protocol.
Any class implementing ``request_approval`` satisfies the protocol without
explicit inheritance (structural subtyping).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


def _new_approval_id() -> str:
    """Generate a stable correlation id for an approval request."""
    return uuid.uuid4().hex


@dataclass
class ApprovalRequest:
    """Immutable request for tool-execution approval.

    Attributes:
        tool_name:   Name of the tool requesting approval.
        arguments:   Arguments the tool will be called with.
        risk_level:  Risk classification (critical / high / medium / low).
        agent_name:  Name of the agent that triggered the call (optional).
        session_id:  Session identifier for tracking (optional).
        context:     Arbitrary context dict for backend-specific data.
        approval_id: Stable correlation id that survives a process restart
                     and can be matched to an inbound channel callback.
                     Auto-generated when not supplied.
    """

    tool_name: str
    arguments: Dict[str, Any]
    risk_level: str
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    approval_id: str = field(default_factory=_new_approval_id)


@dataclass
class ApprovalDecision:
    """Result of an approval request.

    Attributes:
        approved:      Whether execution is allowed.
        reason:        Human-readable reason for the decision.
        modified_args: Optional replacement arguments (empty = use originals).
        approver:      Who/what approved (user, system, webhook, …).
        metadata:      Backend-specific metadata (timestamps, IPs, …).
        scope:         How long the decision should be remembered:
                       ``"once"`` (default — this call only, backward
                       compatible), ``"session"`` (auto-approve matching calls
                       for the rest of this run) or ``"always"`` (persist an
                       allow-rule to disk so future runs don't re-ask). The
                       registry bridges ``session``/``always`` into the durable
                       :class:`PermissionManager` store; ``once`` keeps the
                       existing in-memory fast-path.
        scope_pattern: Optional reusable target/pattern to persist for
                       ``session``/``always`` scopes (e.g. ``"bash:git status *"``
                       or ``"edit:src/app.py"``). When ``None`` the registry
                       derives one from the tool call.
    """

    approved: bool
    reason: str = ""
    modified_args: Dict[str, Any] = field(default_factory=dict)
    approver: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: str = "once"
    scope_pattern: Optional[str] = None


@dataclass
class ApprovalConfig:
    """Configuration for agent-level approval behaviour.

    Follows PraisonAI's ``False/True/Config`` progressive-disclosure pattern:

    - ``approval=False`` — disabled (no approval checks).
    - ``approval=True``  — auto-approve all tools.
    - ``approval=SlackApproval()`` — custom backend, dangerous tools only.
    - ``approval=ApprovalConfig(...)`` — full control.

    Attributes:
        backend:    An :class:`ApprovalProtocol` backend (``SlackApproval``,
                    ``ConsoleBackend``, etc.).  ``None`` falls back to the
                    global :class:`ApprovalRegistry`.
        all_tools:  When ``True`` every tool call goes through approval.
                    When ``False`` (default) only tools in
                    ``DEFAULT_DANGEROUS_TOOLS`` are checked.
        timeout:    Seconds to wait for an approval response.
                    - *positive float* — wait up to that many seconds.
                    - ``None`` — wait **indefinitely** (no timeout).
                    - *unset / 0* — use the backend's own default timeout.
        permissions: Declarative permission rules mapping patterns to actions
                    (e.g., {"read:*": "allow", "bash:rm *": "deny"}).
                    Used for CI-safe, non-interactive permission policies.
    """

    backend: Any = None
    all_tools: bool = False
    timeout: Optional[float] = 0
    permissions: Optional[Dict[str, Any]] = None


@runtime_checkable
class ApprovalProtocol(Protocol):
    """Protocol for tool-execution approval backends.

    Implement ``request_approval`` to create custom approval channels:
    - Console prompts
    - Webhook / HTTP callbacks
    - Messaging platform replies (Slack, WhatsApp, Telegram)
    - External UI dashboards
    - Auto-approve policies

    Example::

        class MyBackend:
            async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
                # … your logic …
                return ApprovalDecision(approved=True)
    """

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Request approval for a tool execution.

        Args:
            request: The approval request with tool info and context.

        Returns:
            ApprovalDecision indicating whether execution is approved.
        """
        ...


@runtime_checkable
class ApprovalStoreProtocol(Protocol):
    """Protocol for durable persistence of pending approvals.

    A store lets pending approvals survive a process restart: requests are
    persisted with a stable ``approval_id``, outstanding ones are re-hydrated
    on startup, and decisions are recorded as a durable audit trail.

    Behaviour is unchanged when no store is configured — in-memory remains the
    zero-dependency default.  Heavy backends (e.g. SQLite) live in the wrapper
    package; this contract lives in core so any backend and any channel can
    interoperate.

    Example::

        class MyStore:
            async def persist(self, approval_id, request, *, expires_at):
                ...
            async def list_pending(self):
                return []
            async def resolve(self, approval_id, decision):
                ...
    """

    async def persist(
        self,
        approval_id: str,
        request: ApprovalRequest,
        *,
        expires_at: float,
    ) -> None:
        """Durably store a pending approval keyed by ``approval_id``."""
        ...

    async def list_pending(self) -> List[Tuple[str, ApprovalRequest]]:
        """Return outstanding (un-resolved, un-expired) pending approvals."""
        ...

    async def resolve(self, approval_id: str, decision: ApprovalDecision) -> None:
        """Record a final decision for ``approval_id`` as an audit trail.

        ``decision.metadata['terminal']`` may carry an explicit terminal state
        (``"approved"``, ``"denied"`` or ``"expired"``) so the timeout path can
        be recorded distinctly from a user denial.  When absent the state is
        derived from ``decision.approved``.
        """
        ...
