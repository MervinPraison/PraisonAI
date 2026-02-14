"""
Bot Approval Backend for PraisonAI.

Sends tool execution approval requests as in-platform messages
(e.g., inline keyboard on Telegram) and waits for user reply.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Default timeout for approval requests (seconds)
DEFAULT_APPROVAL_TIMEOUT = 120


class BotApprovalBackend:
    """In-chat approval backend for bot tool execution.
    
    Sends an approval request message to the user in-chat and waits
    for their reply (yes/no) with a configurable timeout.
    
    Default behavior: deny on timeout (safe by default).
    
    Usage:
        approval = BotApprovalBackend(bot_adapter, timeout=60)
        approved = await approval.request_approval(
            user_id="123",
            channel_id="456",
            tool_name="execute_command",
            tool_args={"command": "ls -la"},
        )
    """
    
    def __init__(
        self,
        adapter: Any = None,
        timeout: float = DEFAULT_APPROVAL_TIMEOUT,
        default_on_timeout: bool = False,
    ):
        self._adapter = adapter
        self._timeout = timeout
        self._default_on_timeout = default_on_timeout
        self._pending: Dict[str, asyncio.Future] = {}
    
    async def request_approval(
        self,
        user_id: str,
        channel_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        description: str = "",
    ) -> bool:
        """Send an approval request and wait for user response.
        
        Args:
            user_id: User to ask for approval
            channel_id: Channel to send the request in
            tool_name: Name of the tool requesting approval
            tool_args: Arguments the tool wants to execute with
            description: Human-readable description of the action
            
        Returns:
            True if approved, False if denied or timed out
        """
        request_id = f"approval_{user_id}_{int(time.time() * 1000)}"
        
        # Format the approval message
        args_preview = str(tool_args)[:200]
        if description:
            msg = f"🔐 Approval required:\n\n{description}\n\nTool: {tool_name}\nArgs: {args_preview}\n\nReply 'yes' to approve or 'no' to deny."
        else:
            msg = f"🔐 Approval required:\n\nTool: {tool_name}\nArgs: {args_preview}\n\nReply 'yes' to approve or 'no' to deny."
        
        # Create a future to wait for the response
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        
        # Send the message
        if self._adapter and hasattr(self._adapter, 'send_message'):
            try:
                await self._adapter.send_message(channel_id, msg)
            except Exception as e:
                logger.error(f"Failed to send approval request: {e}")
                self._pending.pop(request_id, None)
                return self._default_on_timeout
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=self._timeout)
            return result
        except asyncio.TimeoutError:
            logger.info(
                f"Approval request timed out for {tool_name} "
                f"(user={user_id}, default={'approve' if self._default_on_timeout else 'deny'})"
            )
            return self._default_on_timeout
        finally:
            self._pending.pop(request_id, None)
    
    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending approval request.
        
        Args:
            request_id: The approval request ID
            approved: Whether the request is approved
            
        Returns:
            True if the request was found and resolved
        """
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(approved)
            return True
        return False
    
    def resolve_by_user_reply(self, user_id: str, reply_text: str) -> bool:
        """Resolve the most recent pending approval for a user based on reply text.
        
        Args:
            user_id: The user who replied
            reply_text: The reply text (checked for yes/no)
            
        Returns:
            True if a pending request was resolved
        """
        reply_lower = reply_text.strip().lower()
        approved = reply_lower in ("yes", "y", "approve", "ok", "confirm", "1", "true")
        denied = reply_lower in ("no", "n", "deny", "reject", "cancel", "0", "false")
        
        if not approved and not denied:
            return False  # Not an approval response
        
        # Find most recent pending request for this user
        for request_id in reversed(list(self._pending.keys())):
            if f"_{user_id}_" in request_id:
                return self.resolve(request_id, approved)
        
        return False
    
    @property
    def pending_count(self) -> int:
        """Number of pending approval requests."""
        return len(self._pending)
