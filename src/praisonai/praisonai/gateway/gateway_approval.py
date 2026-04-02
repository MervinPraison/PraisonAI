"""
Gateway-backed approval backend for PraisonAI.

Routes tool-execution approval requests through the PraisonAI gateway's
:class:`ExecApprovalManager`.  Implements
:class:`praisonaiagents.approval.protocols.ApprovalProtocol` so it can be
used as a drop-in replacement for ``ConsoleBackend`` or ``AutoApproveBackend``.

This is a *heavy implementation* and lives in the wrapper, not the core SDK.

Design:
  - Fail-closed: if the gateway is unreachable or times out, the tool is DENIED.
  - Async-safe: uses ``asyncio.wait_for`` for timeout management.
  - Thread-safe: safe to share across agents.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from praisonaiagents.approval.protocols import (
    ApprovalDecision,
    ApprovalRequest,
)

from .exec_approval import (
    ExecApprovalManager,
    Resolution,
    get_exec_approval_manager,
)

logger = logging.getLogger(__name__)


class GatewayApprovalBackend:
    """Approval backend that delegates to the gateway's approval queue.

    When an agent calls a dangerous tool, this backend:
    1. Registers a pending request with :class:`ExecApprovalManager`.
    2. Waits (with timeout) for a human to resolve it via the gateway API.
    3. Returns :class:`ApprovalDecision` to the agent.

    If the timeout is reached, the request is **denied** (fail-closed).

    Args:
        manager: Optional :class:`ExecApprovalManager` instance.
                 Falls back to the global singleton.
        timeout: Seconds to wait for a human decision (default 120).
        notify_url: Optional HTTP endpoint to POST a notification when
                    a request is pending (e.g. Slack webhook).

    Example::

        from praisonai.gateway.gateway_approval import GatewayApprovalBackend
        from praisonaiagents import Agent, ApprovalConfig

        backend = GatewayApprovalBackend(timeout=60)
        agent = Agent(
            name="deployer",
            approval=ApprovalConfig(backend=backend, all_tools=True),
        )
    """

    def __init__(
        self,
        manager: Optional[ExecApprovalManager] = None,
        timeout: float = 120.0,
        notify_url: Optional[str] = None,
    ) -> None:
        self._manager = manager
        self._timeout = timeout
        self._notify_url = notify_url

    @property
    def manager(self) -> ExecApprovalManager:
        if self._manager is None:
            self._manager = get_exec_approval_manager()
        return self._manager

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Route the approval request through the gateway.

        Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`.
        """
        request_id, future = await self.manager.register(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_name=request.agent_name or "",
            risk_level=request.risk_level,
        )

        # Fire optional notification (fire-and-forget)
        if self._notify_url:
            asyncio.create_task(self._notify(request_id, request))

        # Wait for resolution (fail-closed on timeout)
        try:
            resolution: Resolution = await asyncio.wait_for(
                future, timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            # Clean up the dangling request from the manager
            self.manager.remove(request_id)
            logger.warning(
                "Approval timeout for request %s (tool=%s) — DENIED",
                request_id, request.tool_name,
            )
            return ApprovalDecision(
                approved=False,
                reason=f"Approval timed out after {self._timeout}s",
                approver="gateway:timeout",
            )

        return ApprovalDecision(
            approved=resolution.approved,
            reason=resolution.reason,
            approver="gateway:human",
        )

    async def _notify(self, request_id: str, request: ApprovalRequest) -> None:
        """POST a notification to the configured webhook (fire-and-forget)."""
        try:
            import aiohttp

            payload = {
                "request_id": request_id,
                "tool_name": request.tool_name,
                "arguments": request.arguments,
                "agent_name": request.agent_name,
                "risk_level": request.risk_level,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._notify_url, json=payload, timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        logger.warning("Notify webhook returned %d", resp.status)
        except ImportError:
            logger.debug("aiohttp not installed — skipping notify webhook")
        except Exception as exc:
            logger.warning("Notify webhook failed: %s", exc)
