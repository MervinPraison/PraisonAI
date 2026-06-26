"""
Presentation-based approval system for tool executions.

Replaces the legacy text-classification approach with structured
interactive UI (buttons) for approval decisions.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots.presentation import MessagePresentation
    from praisonaiagents.approval import ApprovalStoreProtocol

logger = logging.getLogger(__name__)

# Bound replay/audit retention so long-running bots don't grow unboundedly.
# The newest N resolved ids/audit entries are retained; older ones are evicted.
_DEFAULT_HISTORY_LIMIT = 1000


class PresentationApprovalHandler:
    """Handles tool approvals using interactive presentations.

    When an optional :class:`ApprovalStoreProtocol` backend is supplied, pending
    approvals are persisted durably so they survive a process restart: a late
    "Allow"/"Deny" tap that arrives after the restart still resolves, and every
    decision is recorded as an audit trail.  Without a store the handler keeps
    the original in-memory, zero-dependency behaviour.
    """

    def __init__(
        self,
        store: Optional["ApprovalStoreProtocol"] = None,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
    ):
        """Initialize the approval handler.

        Args:
            store: Optional durable store implementing ``ApprovalStoreProtocol``.
                   When ``None`` (default) pending approvals are in-memory only.
            history_limit: Maximum number of resolved approval ids and audit
                entries to retain. Bounds memory for long-running bots; the
                oldest entries are evicted once the limit is exceeded. Replay
                protection still holds for the most recent ``history_limit``
                approvals, which far exceeds any realistic in-flight window.
        """
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_futures: Dict[str, asyncio.Future] = {}
        self._store = store
        # Audit trail of resolved approvals for replay protection and
        # accountability. Records who resolved each approval, the decision,
        # and when. A resolved id is single-use: subsequent callbacks for it
        # are treated as no-ops. Both containers are bounded (FIFO eviction)
        # to avoid unbounded memory growth in long-running bots.
        self._history_limit = max(1, int(history_limit))
        self._audit_log: Deque[Dict[str, Any]] = deque(maxlen=self._history_limit)
        self._resolved_ids: Set[str] = set()
        # Insertion-ordered queue mirroring _resolved_ids for FIFO eviction.
        self._resolved_order: Deque[str] = deque()

    def _mark_resolved(self, approval_id: str) -> None:
        """Record an approval id as resolved with bounded FIFO retention.

        Evicts the oldest resolved id once the configured ``history_limit`` is
        exceeded so replay-protection state cannot grow without bound.
        """
        if approval_id in self._resolved_ids:
            return
        self._resolved_ids.add(approval_id)
        self._resolved_order.append(approval_id)
        while len(self._resolved_order) > self._history_limit:
            oldest = self._resolved_order.popleft()
            self._resolved_ids.discard(oldest)

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str = "medium",
        channel_send_func: Optional[Any] = None,
        target: Optional[str] = None,
        timeout: float = 60.0,
        allowed_actors: Optional[Iterable[str]] = None,
        approval_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request approval for a tool execution using buttons.
        
        Args:
            tool_name: Name of the tool requiring approval
            arguments: Tool arguments to approve
            risk_level: Risk level (low/medium/high)
            channel_send_func: Function to send the presentation
            target: Target chat/channel ID
            timeout: Timeout in seconds
            allowed_actors: Optional set of actor (user) IDs permitted to
                resolve this approval (e.g. the requesting user plus any
                configured ``owner_user_id``/``admin_users``). When provided,
                only these actors may approve/deny; any other clicker is
                rejected. When ``None``, any actor may resolve (legacy
                behaviour, backward compatible).
            approval_id: Optional stable correlation id (auto-generated when
                         omitted) used to match an inbound callback after a
                         restart.
            agent_name: Optional agent that triggered the call (persisted for
                        restart-safe audit).
            session_id: Optional session identifier (persisted for restart-safe
                        audit).

        Returns:
            Dict with 'approved' (bool), 'reason' (str), and 'modified_args' (dict)
        """
        from praisonaiagents.bots.presentation import MessagePresentation
        
        # Generate unique approval ID (stable correlation id). Use the full
        # UUID hex — truncating risks collisions in the durable store.
        if approval_id is None:
            approval_id = uuid.uuid4().hex
        
        # Normalize the authorized actor set (str-typed for cross-platform IDs)
        normalized_actors: Optional[Set[str]] = (
            {str(a) for a in allowed_actors} if allowed_actors is not None else None
        )
        
        # Store approval context
        self._pending_approvals[approval_id] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_level": risk_level,
            "allowed_actors": normalized_actors,
            "target": target,
        }
        
        # Create approval future
        future = asyncio.get_running_loop().create_future()
        self._approval_futures[approval_id] = future

        # Persist pending approval durably (survives restart) if a store exists
        await self._persist_pending(
            approval_id, tool_name, arguments, risk_level, target, timeout,
            agent_name=agent_name, session_id=session_id,
        )

        # Create approval presentation
        presentation = self._create_approval_presentation(
            approval_id, tool_name, arguments, risk_level
        )
        
        # Send presentation if channel function provided. If delivery fails the
        # caller can never resolve, so fail fast instead of waiting out the
        # timeout on an approval no user ever saw — and clear the durable row.
        if channel_send_func and target:
            try:
                await channel_send_func(target, presentation)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to send approval presentation")
                self._pending_approvals.pop(approval_id, None)
                self._approval_futures.pop(approval_id, None)
                result = {
                    "approved": False,
                    "reason": "Failed to deliver approval request",
                    "modified_args": {},
                }
                await self._record_decision(
                    approval_id, result, approver="system", terminal="expired"
                )
                return result
        
        # Wait for approval decision with timeout
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Clean up and record the timeout as a resolution so any late
            # callback for this id is treated as a no-op (replay protection).
            self._pending_approvals.pop(approval_id, None)
            self._approval_futures.pop(approval_id, None)
            self._mark_resolved(approval_id)
            self._audit_log.append({
                "approval_id": approval_id,
                "tool_name": tool_name,
                "actor": None,
                "decision": "timeout",
                "approved": False,
                "timestamp": time.time(),
            })

            result = {
                "approved": False,
                "reason": f"Approval timed out after {timeout} seconds",
                "modified_args": {},
            }
            # Record as an explicit 'expired' terminal state (not 'denied').
            await self._record_decision(
                approval_id, result, approver="system", terminal="expired"
            )
            return result

    async def _persist_pending(
        self,
        approval_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str,
        target: Optional[str],
        timeout: float,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Persist a pending approval to the durable store, if configured."""
        if self._store is None:
            return
        try:
            from praisonaiagents.approval import ApprovalRequest

            request = ApprovalRequest(
                tool_name=tool_name,
                arguments=arguments,
                risk_level=risk_level,
                agent_name=agent_name,
                session_id=session_id,
                context={"target": target} if target else {},
                approval_id=approval_id,
            )
            await self._store.persist(
                approval_id, request, expires_at=time.time() + timeout
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to persist pending approval %s", approval_id)

    async def _record_decision(
        self,
        approval_id: str,
        result: Dict[str, Any],
        approver: Optional[str] = None,
        terminal: Optional[str] = None,
    ) -> Optional[bool]:
        """Record a resolved decision to the durable store, if configured.

        ``terminal`` optionally pins the durable status (``"approved"`` /
        ``"denied"`` / ``"expired"``) so a timeout is audited distinctly from a
        user denial.

        Returns:
            ``None`` when no store is configured (nothing to record).
            Otherwise the store's ``resolve()`` result: ``True`` when a still
            -pending durable row was updated, ``False`` when the row was already
            resolved/expired (a stale callback). A persistence error also yields
            ``False`` so callers can detect that the decision was not durably
            recorded.
        """
        if self._store is None:
            return None
        try:
            from praisonaiagents.approval import ApprovalDecision

            metadata = {"terminal": terminal} if terminal else {}
            decision = ApprovalDecision(
                approved=bool(result.get("approved")),
                reason=result.get("reason", ""),
                modified_args=result.get("modified_args", {}),
                approver=approver,
                metadata=metadata,
            )
            return bool(await self._store.resolve(approval_id, decision))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to record approval decision %s", approval_id)
            return False

    async def rehydrate(self) -> int:
        """Re-hydrate outstanding pending approvals from the durable store.

        Called on startup so a late "Allow"/"Deny" tap that arrives after a
        restart can still be resolved by :meth:`handle_approval_command`.

        Returns:
            Number of pending approvals re-hydrated.  ``0`` when no store is
            configured.
        """
        if self._store is None:
            return 0
        count = 0
        try:
            lister = getattr(self._store, "list_pending", None) or self._store.load_pending
            pending = await lister()
        except Exception:
            logger.exception("Failed to load pending approvals from store")
            return 0
        loop = asyncio.get_running_loop()
        for approval_id, request in pending:
            if approval_id in self._pending_approvals:
                continue
            self._pending_approvals[approval_id] = {
                "tool_name": request.tool_name,
                "arguments": request.arguments,
                "risk_level": request.risk_level,
                "target": (request.context or {}).get("target"),
                # Flag so handle_approval_command treats the durable store as
                # the source of truth and ignores a stale tap on an already
                # expired/resolved row.
                "rehydrated": True,
            }
            self._approval_futures[approval_id] = loop.create_future()
            count += 1
        return count
    
    def _create_approval_presentation(
        self,
        approval_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str,
    ) -> "MessagePresentation":
        """Create an approval presentation with buttons.
        
        Args:
            approval_id: Unique approval ID
            tool_name: Name of the tool
            arguments: Tool arguments
            risk_level: Risk level
            
        Returns:
            MessagePresentation with approval buttons
        """
        from praisonaiagents.bots.presentation import (
            MessagePresentation,
            PresentationBlock,
            PresentationButton,
            PresentationAction,
            ActionType,
            ButtonStyle,
        )
        
        # Format arguments for display
        import json
        args_str = json.dumps(arguments, indent=2, default=str)
        if len(args_str) > 500:
            args_str = args_str[:497] + "..."
        
        # Create prompt text
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚠️")
        prompt = f"{risk_emoji} **Tool Approval Required**\n\nTool: `{tool_name}`\nRisk: {risk_level}\n\nArguments:\n```\n{args_str}\n```"
        
        # Create approval buttons
        buttons = [
            PresentationButton(
                label="✅ Approve",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} allow"
                ),
                style=ButtonStyle.SUCCESS,
                priority=10,
            ),
            PresentationButton(
                label="❌ Deny",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} deny"
                ),
                style=ButtonStyle.DANGER,
                priority=9,
            ),
        ]
        
        # Add "Always Allow" for low-risk tools
        if risk_level == "low":
            buttons.insert(1, PresentationButton(
                label="✅ Always Allow",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} always"
                ),
                style=ButtonStyle.PRIMARY,
                priority=8,
            ))
        
        # Create presentation
        return MessagePresentation(blocks=[
            PresentationBlock.make_text(prompt),
            PresentationBlock.make_buttons(buttons),
            PresentationBlock.make_context(f"Approval ID: {approval_id}"),
        ])
    
    def is_authorized(self, approval_id: str, actor: Optional[str]) -> bool:
        """Check whether ``actor`` may resolve the given pending approval.

        Args:
            approval_id: The approval ID
            actor: The resolving user's ID (may be ``None`` if the channel
                could not determine it)

        Returns:
            True if the approval has no actor restriction, or ``actor`` is in
            the approval's ``allowed_actors`` set. False otherwise (including
            when the approval is unknown/already resolved).
        """
        context = self._pending_approvals.get(approval_id)
        if context is None:
            return False
        allowed_actors = context.get("allowed_actors")
        if allowed_actors is None:
            return True
        return actor is not None and str(actor) in allowed_actors

    async def handle_approval_command(
        self,
        approval_id: str,
        decision: str,
        modified_args: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
        approver: Optional[str] = None,
    ) -> bool:
        """Handle an approval command from a button click.
        
        Args:
            approval_id: The approval ID
            decision: The decision (allow/deny/always)
            modified_args: Optional modified arguments
            actor: ID of the user resolving the approval. When the approval
                was created with ``allowed_actors``, the actor must be a member
                of that set or the callback is rejected (and the pending
                approval is left intact for an authorized actor to resolve).
            approver: Optional identity of who approved (for the durable audit
                trail). Defaults to ``actor`` when omitted.
            
        Returns:
            True if handled, False if the approval is unknown, already
            resolved (replay), or the actor is not authorized.
        """
        # Replay protection: an already-resolved id is single-use.
        if approval_id in self._resolved_ids:
            logger.warning(
                f"Approval {approval_id} already resolved; ignoring duplicate "
                f"callback from actor '{actor}'"
            )
            return False

        # Check if approval exists
        if approval_id not in self._pending_approvals:
            logger.warning(f"Approval {approval_id} not found or already processed")
            return False
        
        # Enforce actor authorization. Do NOT pop the pending approval on an
        # unauthorized attempt, so the legitimate actor can still resolve it.
        if not self.is_authorized(approval_id, actor):
            logger.warning(
                f"Actor '{actor}' not authorized for approval {approval_id}; "
                f"rejecting"
            )
            self._audit_log.append({
                "approval_id": approval_id,
                "tool_name": self._pending_approvals[approval_id].get("tool_name"),
                "actor": str(actor) if actor is not None else None,
                "decision": decision,
                "approved": False,
                "authorized": False,
                "timestamp": time.time(),
            })
            return False
        
        # Peek at context without committing to resolution yet. A rehydrated
        # approval may already be expired/resolved in the durable store, in
        # which case this is a stale tap and must not look handled.
        context = self._pending_approvals[approval_id]
        is_rehydrated = self._approval_futures.get(approval_id) is None or context.get(
            "rehydrated", False
        )

        # Create result
        result = {
            "approved": decision in ("allow", "always"),
            "reason": f"User clicked {decision} button",
            "modified_args": modified_args or {},
        }

        # Add always-allow flag if applicable
        if decision == "always":
            result["always_allow"] = True
            result["reason"] = "User granted permanent approval for this tool"

        # Record the decision durably (audit trail + survives the waiter).
        # Default the durable approver to the resolving actor when not given.
        recorded = await self._record_decision(
            approval_id, result, approver=approver or actor
        )

        # For a rehydrated approval (no original waiter), the durable store is
        # the source of truth. If resolve() matched no pending row (already
        # expired/resolved), this is a stale tap: do not mark it handled, and
        # leave state untouched so the audit trail stays accurate.
        if recorded is False and is_rehydrated:
            logger.warning(
                "Ignoring stale callback for approval %s from actor '%s' "
                "(durable row already resolved or expired)",
                approval_id,
                actor,
            )
            return False

        # Commit the resolution (single-use from here on).
        self._pending_approvals.pop(approval_id, None)
        future = self._approval_futures.pop(approval_id, None)
        self._mark_resolved(approval_id)

        # Record the resolution for audit (who/what/when/decision)
        self._audit_log.append({
            "approval_id": approval_id,
            "tool_name": context.get("tool_name"),
            "actor": str(actor) if actor is not None else None,
            "decision": decision,
            "approved": result["approved"],
            "authorized": True,
            "timestamp": time.time(),
        })

        # Complete the future (may be absent after a restart re-hydration)
        if future is not None and not future.done():
            future.set_result(result)
        
        return True
    
    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        """Return the immutable-ish audit trail of resolved approvals.

        Each entry records ``approval_id``, ``tool_name``, ``actor``,
        ``decision``, ``approved``, and ``timestamp``. Entries are copied so
        callers cannot mutate the handler's internal audit trail.
        """
        return [dict(entry) for entry in self._audit_log]
    
    def parse_approval_callback(self, callback_data: str) -> Optional[Dict[str, str]]:
        """Parse approval callback data from button clicks.
        
        Args:
            callback_data: Callback data from button click
            
        Returns:
            Dict with 'approval_id' and 'decision' if valid, None otherwise
        """
        # Handle command-style callbacks (cmd:/approve <id> <decision>)
        if callback_data.startswith("cmd:"):
            parts = callback_data[4:].split()
            if len(parts) >= 3 and parts[0] == "/approve":
                return {
                    "approval_id": parts[1],
                    "decision": parts[2],
                }
        
        # Handle direct approval callbacks
        if callback_data.startswith("approve:"):
            parts = callback_data[8:].split(":", 1)
            if len(parts) == 2:
                return {
                    "approval_id": parts[0],
                    "decision": parts[1],
                }
        
        return None
    
    def cleanup(self) -> None:
        """Clean up in-memory pending approvals.

        In-memory futures are cancelled, but when a durable store is configured
        the persisted pending rows remain on disk so a late tap after a restart
        is still resolvable via :meth:`rehydrate`.
        """
        # Cancel all pending futures
        for future in self._approval_futures.values():
            if not future.done():
                future.cancel()
        
        self._pending_approvals.clear()
        self._approval_futures.clear()


# Global instance for convenience
_global_handler = None


def get_approval_handler(
    store: Optional["ApprovalStoreProtocol"] = None,
) -> PresentationApprovalHandler:
    """Get the global approval handler instance.

    Args:
        store: Optional durable store. Applied to the global handler when it is
               first created, or attached to an existing handler that has none.
    """
    global _global_handler
    if _global_handler is None:
        _global_handler = PresentationApprovalHandler(store=store)
    elif store is not None and _global_handler._store is None:
        _global_handler._store = store
    return _global_handler