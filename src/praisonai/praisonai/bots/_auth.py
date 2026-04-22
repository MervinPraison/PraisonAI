"""
Unknown User Handler for PraisonAI Bots.

Handles unknown users according to the configured policy:
- deny: Drop messages silently (backward compatible)
- allow: Allow all users  
- pair: Use pairing flow for owner approval

Shared across all bot adapters (Telegram, Discord, Slack, WhatsApp).
"""

import logging
import time
from typing import Optional, Literal, Dict, Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots import BotConfig, BotMessage
    from praisonai.gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


class UnknownUserHandler:
    """Handler for unknown users in bot interactions.
    
    Provides centralized logic for handling users not in the allowed_users list.
    Supports rate limiting and pairing flow for secure user approval.
    """
    
    def __init__(
        self, 
        config: "BotConfig", 
        pairing_store: Optional["PairingStore"] = None,
        send_message_callback: Optional[Callable] = None
    ):
        self.config = config
        self.pairing_store = pairing_store
        self.send_message_callback = send_message_callback
        
        # Rate limiting: user_id -> last_code_generation_time
        self._rate_limits: Dict[str, float] = {}
        self._rate_limit_window = 600  # 10 minutes
        
    async def handle(self, message: "BotMessage") -> Literal["allow", "drop"]:
        """Handle an unknown user message according to policy.
        
        Args:
            message: The bot message from unknown user
            
        Returns:
            "allow" if message should be processed, "drop" if it should be ignored
        """
        user_id = message.sender.user_id if message.sender else ""
        platform = message.channel.channel_type if message.channel else "unknown"
        
        # Check if user is actually allowed
        if self.config.is_user_allowed(user_id):
            return "allow"
        
        # Apply policy
        if self.config.unknown_user_policy == "deny":
            logger.debug(f"Dropping message from unknown user {user_id} (policy: deny)")
            return "drop"
        
        if self.config.unknown_user_policy == "allow":
            return "allow"
            
        if self.config.unknown_user_policy == "pair":
            return await self._handle_pairing(message, user_id, platform)
        
        # Fallback to deny
        logger.warning(f"Unknown policy '{self.config.unknown_user_policy}', falling back to deny")
        return "drop"
    
    async def _handle_pairing(self, message: "BotMessage", user_id: str, platform: str) -> Literal["allow", "drop"]:
        """Handle pairing flow for unknown user.
        
        Returns:
            "allow" if user is already paired, "drop" after sending pairing code
        """
        if not self.pairing_store:
            logger.warning("Pairing policy set but no pairing store available")
            return "drop"
        
        # Check if already paired
        if self.pairing_store.is_paired(user_id, platform):
            logger.debug(f"User {user_id} already paired for {platform}")
            return "allow"
        
        # Rate limiting check
        now = time.time()
        last_code_time = self._rate_limits.get(user_id, 0)
        if now - last_code_time < self._rate_limit_window:
            logger.debug(f"Rate limited user {user_id} (last code: {now - last_code_time:.1f}s ago)")
            return "drop"
        
        # Generate pairing code and send to user
        try:
            code = self.pairing_store.generate_code(channel_type=platform, channel_id=user_id)
            self._rate_limits[user_id] = now
            
            # Send pairing instructions to user
            await self._send_pairing_instructions(message, code, platform)
            
            logger.info(f"Generated pairing code for {user_id} on {platform}: {code}")
            
        except Exception as e:
            logger.error(f"Failed to generate pairing code for {user_id}: {e}")
        
        return "drop"  # Always drop after pairing flow
    
    async def _send_pairing_instructions(self, message: "BotMessage", code: str, platform: str):
        """Send pairing instructions to the user.
        
        Uses the callback provided during initialization, or logs if not available.
        """
        instructions = (
            f"Your pairing code: `{code}`\n"
            f"Owner: `praisonai pairing approve {platform} {code}`"
        )
        
        # Try to use the send message callback
        if self.send_message_callback and message.channel:
            try:
                await self.send_message_callback(message.channel.channel_id, instructions)
            except Exception as e:
                logger.warning(f"Failed to send pairing instructions: {e}")
        else:
            logger.warning(f"Cannot send pairing instructions - no callback available")
            logger.info(f"Pairing instructions for {message.sender.user_id if message.sender else 'unknown'}: {instructions}")
