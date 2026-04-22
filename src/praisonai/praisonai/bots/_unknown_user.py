"""
Unknown user handler for bot pairing approval system.

Handles incoming messages from unknown users and orchestrates the pairing
approval process with owner DM notifications.
"""

import logging
from typing import Any, Dict, Optional, Protocol

from praisonaiagents.bots import BotMessage
from praisonaiagents.bots.pairing_types import PairingReply, UnknownUserPolicy
from praisonai.gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


class BotAdapter(Protocol):
    """Protocol for bot adapters that can send messages and approval DMs."""
    
    async def send_approval_dm(
        self, 
        owner_user_id: str, 
        user_name: str, 
        code: str, 
        channel: str,
        user_id: str
    ) -> Optional[str]:
        """Send approval DM to owner with inline buttons.
        
        Returns:
            Message ID if sent successfully, None if failed.
        """
        ...
    
    async def reply(self, chat_id: str, text: str) -> None:
        """Reply to a chat/DM with a text message."""
        ...


class BotContext:
    """Context object containing bot configuration and pairing store."""
    
    def __init__(
        self, 
        config: Any,  # BotConfig
        pairing_store: Optional[PairingStore] = None,
        adapter: Optional[BotAdapter] = None
    ):
        self.config = config
        self.pairing_store = pairing_store or PairingStore()
        self.adapter = adapter


class UnknownUserHandler:
    """Handles unknown user messages and orchestrates pairing approval."""
    
    @classmethod
    async def handle(cls, message: BotMessage, bot_ctx: BotContext) -> bool:
        """Handle message from unknown user.
        
        Args:
            message: The incoming bot message
            bot_ctx: Bot context with config and adapters
            
        Returns:
            True if message was handled (user was processed), False if it should be dropped
        """
        if not message.sender:
            return False
            
        user_id = message.sender.user_id
        user_name = message.sender.display_name or message.sender.username or user_id
        channel = message.channel.channel_id if message.channel else "dm"
        
        # Determine channel type from message or context
        # This would be set by the specific bot implementation
        channel_type = getattr(message, '_channel_type', 'unknown')
        
        # Check if user is already paired
        if bot_ctx.pairing_store.is_paired(user_id, channel_type):
            return True  # User is approved, let message through
        
        unknown_policy = getattr(bot_ctx.config, 'unknown_user_policy', 'deny')
        
        if unknown_policy == "allow":
            # Auto-approve and pair the user
            bot_ctx.pairing_store.verify_and_pair(
                code="auto", 
                channel_id=user_id, 
                channel_type=channel_type,
                label=f"Auto-approved: {user_name}"
            )
            return True
            
        elif unknown_policy == "deny":
            # Silently drop (existing behavior)
            return False
            
        elif unknown_policy == "pair":
            return await cls._handle_pairing_request(
                message, bot_ctx, user_id, user_name, channel, channel_type
            )
            
        return False
    
    @classmethod
    async def _handle_pairing_request(
        cls, 
        message: BotMessage, 
        bot_ctx: BotContext, 
        user_id: str,
        user_name: str, 
        channel: str,
        channel_type: str
    ) -> bool:
        """Handle the pairing request workflow."""
        # Generate pairing code
        try:
            code = bot_ctx.pairing_store.generate_code(channel_type=channel_type)
        except RuntimeError as e:
            logger.error(f"Failed to generate pairing code: {e}")
            if bot_ctx.adapter:
                await bot_ctx.adapter.reply(
                    channel, 
                    "Sorry, the system is busy. Please try again later."
                )
            return False
        
        # Check if owner is configured for inline approval
        owner_user_id = getattr(bot_ctx.config, 'owner_user_id', None)
        
        if owner_user_id and bot_ctx.adapter:
            # Send approval DM to owner with inline buttons
            try:
                message_id = await bot_ctx.adapter.send_approval_dm(
                    owner_user_id=owner_user_id,
                    user_name=user_name,
                    code=code,
                    channel=channel,
                    user_id=user_id
                )
                
                if message_id:
                    # Notify user that request was sent
                    await bot_ctx.adapter.reply(
                        channel, 
                        "Your request has been sent to the owner for approval."
                    )
                else:
                    # Fallback to CLI instruction
                    await cls._send_cli_fallback(bot_ctx, channel, code, channel_type)
                    
            except Exception as e:
                logger.error(f"Failed to send approval DM: {e}")
                await cls._send_cli_fallback(bot_ctx, channel, code, channel_type)
        else:
            # No owner configured, fallback to CLI
            await cls._send_cli_fallback(bot_ctx, channel, code, channel_type)
        
        return False  # Don't process the message until approved
    
    @classmethod
    async def _send_cli_fallback(
        cls, 
        bot_ctx: BotContext, 
        channel: str, 
        code: str, 
        channel_type: str
    ) -> None:
        """Send CLI fallback instructions."""
        if bot_ctx.adapter:
            await bot_ctx.adapter.reply(
                channel,
                f"Your pairing code: {code}. "
                f"Ask the owner to run: praisonai pairing approve {channel_type} {code}"
            )