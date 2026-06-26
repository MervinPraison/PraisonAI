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
from typing import Any, Dict, Iterable, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots.presentation import MessagePresentation

logger = logging.getLogger(__name__)


class PresentationApprovalHandler:
    """Handles tool approvals using interactive presentations."""
    
    def __init__(self):
        """Initialize the approval handler."""
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_futures: Dict[str, asyncio.Future] = {}
        # Audit trail of resolved approvals for replay protection and
        # accountability. Records who resolved each approval, the decision,
        # and when. A resolved id is single-use: subsequent callbacks for it
        # are treated as no-ops.
        self._audit_log: List[Dict[str, Any]] = []
        self._resolved_ids: Set[str] = set()
    
    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str = "medium",
        channel_send_func: Optional[Any] = None,
        target: Optional[str] = None,
        timeout: float = 60.0,
        allowed_actors: Optional[Iterable[str]] = None,
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
            
        Returns:
            Dict with 'approved' (bool), 'reason' (str), and 'modified_args' (dict)
        """
        from praisonaiagents.bots.presentation import MessagePresentation
        
        # Generate unique approval ID
        approval_id = str(uuid.uuid4())[:8]
        
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
        }
        
        # Create approval future
        future = asyncio.get_running_loop().create_future()
        self._approval_futures[approval_id] = future
        
        # Create approval presentation
        presentation = self._create_approval_presentation(
            approval_id, tool_name, arguments, risk_level
        )
        
        # Send presentation if channel function provided
        if channel_send_func and target:
            try:
                await channel_send_func(target, presentation)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Failed to send approval presentation")
        
        # Wait for approval decision with timeout
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Clean up and record the timeout as a resolution so any late
            # callback for this id is treated as a no-op (replay protection).
            self._pending_approvals.pop(approval_id, None)
            self._approval_futures.pop(approval_id, None)
            self._resolved_ids.add(approval_id)
            self._audit_log.append({
                "approval_id": approval_id,
                "tool_name": tool_name,
                "actor": None,
                "decision": "timeout",
                "approved": False,
                "timestamp": time.time(),
            })
            
            return {
                "approved": False,
                "reason": f"Approval timed out after {timeout} seconds",
                "modified_args": {},
            }
    
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
        
        # Get approval context (single-use from here on)
        context = self._pending_approvals.pop(approval_id)
        future = self._approval_futures.pop(approval_id, None)
        self._resolved_ids.add(approval_id)
        
        if not future:
            return False
        
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
        
        # Complete the future
        if not future.done():
            future.set_result(result)
        
        return True
    
    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        """Return the immutable-ish audit trail of resolved approvals.

        Each entry records ``approval_id``, ``tool_name``, ``actor``,
        ``decision``, ``approved``, and ``timestamp``.
        """
        return list(self._audit_log)
    
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
        """Clean up pending approvals."""
        # Cancel all pending futures
        for future in self._approval_futures.values():
            if not future.done():
                future.cancel()
        
        self._pending_approvals.clear()
        self._approval_futures.clear()


# Global instance for convenience
_global_handler = None


def get_approval_handler() -> PresentationApprovalHandler:
    """Get the global approval handler instance."""
    global _global_handler
    if _global_handler is None:
        _global_handler = PresentationApprovalHandler()
    return _global_handler