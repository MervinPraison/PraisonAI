"""
Pairing UI components for inline buttons and callback handling.

Provides platform-specific UI builders and callback dispatchers for the
pairing approval system.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from praisonaiagents.bots.pairing_types import PairingApprovalResult

logger = logging.getLogger(__name__)


def _get_callback_secret() -> str:
    """Get HMAC secret for callback payload verification."""
    import os
    import secrets
    return os.environ.get("PRAISONAI_CALLBACK_SECRET", "") or secrets.token_hex(16)


class PairingUIBuilder:
    """Builds platform-specific inline UI for pairing approval."""
    
    @staticmethod
    def create_telegram_keyboard(user_name: str, code: str, channel: str, user_id: str) -> Dict[str, Any]:
        """Create Telegram inline keyboard for approval."""
        approve_data = f"pair:approve:{channel}:{code}"
        deny_data = f"pair:deny:{channel}:{code}"
        
        # Add HMAC signature to prevent tampering
        secret = _get_callback_secret().encode()
        approve_sig = hmac.new(secret, approve_data.encode(), hashlib.sha256).hexdigest()[:8]
        deny_sig = hmac.new(secret, deny_data.encode(), hashlib.sha256).hexdigest()[:8]
        
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve",
                        "callback_data": f"{approve_data}:{approve_sig}"
                    },
                    {
                        "text": "❌ Deny", 
                        "callback_data": f"{deny_data}:{deny_sig}"
                    }
                ]
            ]
        }
    
    @staticmethod
    def create_discord_components(user_name: str, code: str, channel: str, user_id: str) -> list:
        """Create Discord button components for approval."""
        approve_id = f"pair:approve:{channel}:{code}"
        deny_id = f"pair:deny:{channel}:{code}"
        
        # Add HMAC signature
        secret = _get_callback_secret().encode()
        approve_sig = hmac.new(secret, approve_id.encode(), hashlib.sha256).hexdigest()[:8]
        deny_sig = hmac.new(secret, deny_id.encode(), hashlib.sha256).hexdigest()[:8]
        
        return [
            {
                "type": 1,  # Action row
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 3,  # Success (green)
                        "label": "✅ Approve",
                        "custom_id": f"{approve_id}:{approve_sig}"
                    },
                    {
                        "type": 2,  # Button
                        "style": 4,  # Danger (red)
                        "label": "❌ Deny",
                        "custom_id": f"{deny_id}:{deny_sig}"
                    }
                ]
            }
        ]
    
    @staticmethod
    def create_slack_blocks(user_name: str, code: str, channel: str, user_id: str) -> list:
        """Create Slack block kit for approval."""
        approve_value = f"pair:approve:{channel}:{code}"
        deny_value = f"pair:deny:{channel}:{code}"
        
        # Add HMAC signature
        secret = _get_callback_secret().encode()
        approve_sig = hmac.new(secret, approve_value.encode(), hashlib.sha256).hexdigest()[:8]
        deny_sig = hmac.new(secret, deny_value.encode(), hashlib.sha256).hexdigest()[:8]
        
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{user_name}* wants to chat. Approve access?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Approve"
                        },
                        "style": "primary",
                        "value": f"{approve_value}:{approve_sig}",
                        "action_id": "pair_approve"
                    },
                    {
                        "type": "button", 
                        "text": {
                            "type": "plain_text",
                            "text": "❌ Deny"
                        },
                        "style": "danger",
                        "value": f"{deny_value}:{deny_sig}",
                        "action_id": "pair_deny"
                    }
                ]
            }
        ]


class PairingCallbackHandler:
    """Handles callback data from inline buttons."""
    
    def __init__(self, pairing_store):
        self.pairing_store = pairing_store
    
    def parse_and_verify_callback(self, callback_data: str) -> Optional[Dict[str, str]]:
        """Parse and verify callback data from button press.
        
        Args:
            callback_data: Raw callback data (e.g., "pair:approve:telegram:abc123:sig")
            
        Returns:
            Parsed data dict or None if invalid
        """
        try:
            parts = callback_data.split(":")
            if len(parts) < 5 or parts[0] != "pair":
                return None
            
            action = parts[1]  # approve/deny
            channel = parts[2]  # telegram/discord/slack
            code = parts[3]     # pairing code
            signature = parts[4] # HMAC signature
            
            # Verify signature
            payload = f"pair:{action}:{channel}:{code}"
            secret = _get_callback_secret().encode()
            expected_sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:8]
            
            if not hmac.compare_digest(signature, expected_sig):
                logger.warning(f"Invalid callback signature: {callback_data}")
                return None
            
            return {
                "action": action,
                "channel": channel, 
                "code": code
            }
            
        except Exception as e:
            logger.error(f"Failed to parse callback data: {e}")
            return None
    
    async def handle_approval_callback(
        self, 
        callback_data: str, 
        owner_user_id: str,
        bot_adapter: Any
    ) -> PairingApprovalResult:
        """Handle approval/denial callback from owner.
        
        Args:
            callback_data: Button callback data
            owner_user_id: User ID of the owner who clicked
            bot_adapter: Bot adapter for sending notifications
            
        Returns:
            Result of the approval action
        """
        parsed = self.parse_and_verify_callback(callback_data)
        if not parsed:
            return PairingApprovalResult(
                success=False,
                message="Invalid or tampered callback data"
            )
        
        action = parsed["action"]
        channel = parsed["channel"]
        code = parsed["code"]
        
        if action == "approve":
            # Approve the pairing
            success = self.pairing_store.verify_and_pair(
                code=code,
                channel_id=owner_user_id,  # This would be the original user_id
                channel_type=channel,
                label=f"Approved by {owner_user_id}"
            )
            
            if success:
                # Notify original user
                try:
                    await bot_adapter.reply(
                        owner_user_id,  # This should be the original requester
                        "You've been approved! Send me a message."
                    )
                except Exception as e:
                    logger.error(f"Failed to notify approved user: {e}")
                
                return PairingApprovalResult(
                    success=True,
                    message="✅ Approved",
                    user_id=owner_user_id,
                    channel=channel
                )
            else:
                return PairingApprovalResult(
                    success=False,
                    message="❌ Failed to approve (code may be expired)"
                )
                
        elif action == "deny":
            # Revoke if was temporarily added, or just ignore
            # Note: In real implementation, we'd need to track the original user_id
            return PairingApprovalResult(
                success=True,
                message="❌ Denied",
                channel=channel
            )
        
        return PairingApprovalResult(
            success=False,
            message="Unknown action"
        )