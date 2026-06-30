"""
Durable, actor-authorised :class:`ApprovalProtocol` backend.

Wires the otherwise-orphaned :class:`PresentationApprovalHandler` (+ optional
:class:`ApprovalStore`) into the standard ``ApprovalProtocol`` contract used by
``Agent(approval=...)`` and every chat channel.

Unlike the bespoke per-channel backends (``TelegramApproval``,
``SlackApproval``, ``DiscordApproval``, …) this path:

* **Authorises** the approver against an ``allowed_actors`` set, so a stranger
  or unrelated group member cannot approve a privileged tool/exec call.
* **Persists** pending approvals to SQLite and **rehydrates** them on restart,
  so an in-flight decision survives a process restart.
* Carries an **unguessable approval id** in the button callback payload, so a
  decision binds to a specific request instead of being matched by message id.
* Does **not** route the allow/deny decision through an LLM classifier.

The backend is transport-agnostic: a channel supplies an async
``channel_send_func(target, presentation)`` that renders the approval
presentation (buttons) on the wire, and feeds button taps back in via
:meth:`handle_callback`.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, Set

from ._presentation_approval import PresentationApprovalHandler

logger = logging.getLogger(__name__)


class PresentationApprovalBackend:
    """``ApprovalProtocol`` backend backed by :class:`PresentationApprovalHandler`.

    Satisfies :class:`praisonaiagents.approval.protocols.ApprovalProtocol`
    (structural ``request_approval(request) -> ApprovalDecision``) while adding
    actor-authorisation, durable persistence and replay protection.

    Args:
        store: Optional durable store implementing ``ApprovalStoreProtocol``
            (e.g. :class:`ApprovalStore`). When supplied, pending approvals are
            persisted and survive a restart.
        allowed_actors: Optional set of actor (user) IDs permitted to resolve an
            approval (owner / operator scope). When ``None`` any actor may
            resolve (legacy, backward-compatible behaviour).
        channel_send_func: Optional async callable ``(target, presentation)``
            used to render the approval presentation on a chat channel.
        target: Optional default channel/chat id passed to ``channel_send_func``.
        timeout: Seconds to wait for a decision before failing closed.
    """

    def __init__(
        self,
        store: Optional[Any] = None,
        allowed_actors: Optional[Iterable[str]] = None,
        channel_send_func: Optional[Any] = None,
        target: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self._handler = PresentationApprovalHandler(store=store)
        self._allowed_actors: Optional[Set[str]] = (
            {str(a) for a in allowed_actors} if allowed_actors is not None else None
        )
        self._channel_send_func = channel_send_func
        self._target = target
        self._timeout = timeout

    @property
    def handler(self) -> PresentationApprovalHandler:
        """The underlying durable, authorised approval handler."""
        return self._handler

    @property
    def audit_log(self):
        """Audit trail of resolved approvals (who/what/decision/when)."""
        return self._handler.audit_log

    async def rehydrate(self) -> int:
        """Restore outstanding pending approvals from the durable store.

        Call once on startup so a late "Allow"/"Deny" tap that arrives after a
        restart still resolves. The backend's configured ``allowed_actors`` are
        re-applied to every rehydrated approval so a restart does not silently
        drop the actor authorisation that secured the original request.
        Returns the number re-hydrated (0 with no store).
        """
        return await self._handler.rehydrate(allowed_actors=self._allowed_actors)

    async def handle_callback(
        self,
        approval_id: str,
        decision: str,
        actor: Optional[str] = None,
        approver: Optional[str] = None,
        modified_args: Optional[dict] = None,
    ) -> bool:
        """Resolve a pending approval from an inbound button tap.

        The ``approval_id`` is the unguessable id carried in the button's
        callback payload. Only an actor in ``allowed_actors`` may resolve.
        Returns ``True`` when handled, ``False`` when unknown, already resolved
        (replay), or the actor is not authorised.
        """
        return await self._handler.handle_approval_command(
            approval_id,
            decision,
            modified_args=modified_args,
            actor=actor,
            approver=approver,
        )

    # ── ApprovalProtocol ────────────────────────────────────────────────
    async def request_approval(self, request) -> Any:
        """Request approval for a tool execution (``ApprovalProtocol``).

        Authorises against ``allowed_actors``, persists durably, and waits for a
        decision carrying the request's unguessable ``approval_id``.
        """
        from praisonaiagents.approval.protocols import ApprovalDecision

        target = (request.context or {}).get("target") or self._target

        result = await self._handler.request_approval(
            tool_name=request.tool_name,
            arguments=request.arguments,
            risk_level=request.risk_level,
            channel_send_func=self._channel_send_func,
            target=target,
            timeout=self._timeout,
            allowed_actors=self._allowed_actors,
            approval_id=request.approval_id,
            agent_name=request.agent_name,
            session_id=request.session_id,
        )

        return ApprovalDecision(
            approved=bool(result.get("approved")),
            reason=result.get("reason", ""),
            modified_args=result.get("modified_args", {}),
            metadata={"approval_id": request.approval_id},
        )

    def request_approval_sync(self, request) -> Any:
        """Synchronous wrapper for :meth:`request_approval`."""
        from .._async_bridge import run_sync

        return run_sync(self.request_approval(request), timeout=self._timeout)


__all__ = ["PresentationApprovalBackend"]
