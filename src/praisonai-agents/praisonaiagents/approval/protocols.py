"""
Approval protocol definitions for PraisonAI Agents.

Defines the structural contract for approval backends via typing.Protocol.
Any class implementing ``request_approval`` satisfies the protocol without
explicit inheritance (structural subtyping).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class ApprovalRequest:
    """Immutable request for tool-execution approval.

    Attributes:
        tool_name:  Name of the tool requesting approval.
        arguments:  Arguments the tool will be called with.
        risk_level: Risk classification (critical / high / medium / low).
        agent_name: Name of the agent that triggered the call (optional).
        session_id: Session identifier for tracking (optional).
        context:    Arbitrary context dict for backend-specific data.
    """

    tool_name: str
    arguments: Dict[str, Any]
    risk_level: str
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalDecision:
    """Result of an approval request.

    Attributes:
        approved:      Whether execution is allowed.
        reason:        Human-readable reason for the decision.
        modified_args: Optional replacement arguments (empty = use originals).
        approver:      Who/what approved (user, system, webhook, …).
        metadata:      Backend-specific metadata (timestamps, IPs, …).
    """

    approved: bool
    reason: str = ""
    modified_args: Dict[str, Any] = field(default_factory=dict)
    approver: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


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
