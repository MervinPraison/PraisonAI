"""
Presentation-based approval system for tool executions.

Replaces the legacy text-classification approach with structured
interactive UI (buttons) for approval decisions.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots.presentation import MessagePresentation

logger = logging.getLogger(__name__)


class PresentationApprovalHandler:
    """Handles tool approvals using interactive presentations."""
    
    def __init__(self):
        """Initialize the approval handler."""
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._approval_futures: Dict[str, asyncio.Future] = {}
    
    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: str = "medium",
        channel_send_func: Optional[Any] = None,
        target: Optional[str] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """Request approval for a tool execution using buttons.
        
        Args:
            tool_name: Name of the tool requiring approval
            arguments: Tool arguments to approve
            risk_level: Risk level (low/medium/high)
            channel_send_func: Function to send the presentation
            target: Target chat/channel ID
            timeout: Timeout in seconds
            
        Returns:
            Dict with 'approved' (bool), 'reason' (str), and 'modified_args' (dict)
        """
        from praisonaiagents.bots.presentation import MessagePresentation
        
        # Generate unique approval ID
        approval_id = str(uuid.uuid4())[:8]
        
        # Store approval context
        self._pending_approvals[approval_id] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_level": risk_level,
        }
        
        # Create approval future
        future = asyncio.get_event_loop().create_future()
        self._approval_futures[approval_id] = future
        
        # Create approval presentation
        presentation = self._create_approval_presentation(
            approval_id, tool_name, arguments, risk_level
        )
        
        # Send presentation if channel function provided
        if channel_send_func and target:
            try:
                await channel_send_func(target, presentation)
            except Exception as e:
                logger.error(f"Failed to send approval presentation: {e}")
        
        # Wait for approval decision with timeout
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Clean up
            self._pending_approvals.pop(approval_id, None)
            self._approval_futures.pop(approval_id, None)
            
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
            PresentationBlock.text(prompt),
            PresentationBlock.make_buttons(buttons),
            PresentationBlock.context(f"Approval ID: {approval_id}"),
        ])
    
    async def handle_approval_command(
        self,
        approval_id: str,
        decision: str,
        modified_args: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Handle an approval command from a button click.
        
        Args:
            approval_id: The approval ID
            decision: The decision (allow/deny/always)
            modified_args: Optional modified arguments
            
        Returns:
            True if handled, False if approval not found
        """
        # Check if approval exists
        if approval_id not in self._pending_approvals:
            logger.warning(f"Approval {approval_id} not found or already processed")
            return False
        
        # Get approval context
        context = self._pending_approvals.pop(approval_id)
        future = self._approval_futures.pop(approval_id, None)
        
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
        
        # Complete the future
        if not future.done():
            future.set_result(result)
        
        return True
    
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