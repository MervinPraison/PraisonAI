"""
Integration tests for pairing owner DM approval system.

Tests the real flow with stub adapters to verify end-to-end functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List

from praisonaiagents.bots import BotMessage, BotUser, BotChannel, MessageType
from praisonaiagents.bots.config import BotConfig
from praisonaiagents.bots.pairing_types import PairingApprovalResult
from praisonai.bots._unknown_user import UnknownUserHandler, BotContext
from praisonai.bots._pairing_ui import PairingCallbackHandler, PairingUIBuilder
from praisonai.gateway.pairing import PairingStore


class StubBotAdapter:
    """Stub adapter for testing pairing functionality."""
    
    def __init__(self):
        self.sent_messages: List[Dict] = []
        self.approval_dms: List[Dict] = []
    
    async def send_approval_dm(
        self, 
        owner_user_id: str, 
        user_name: str, 
        code: str, 
        channel: str,
        user_id: str
    ) -> str:
        """Record approval DM sent."""
        dm_data = {
            "to": owner_user_id,
            "user_name": user_name, 
            "code": code,
            "channel": channel,
            "user_id": user_id
        }
        self.approval_dms.append(dm_data)
        return f"msg_{len(self.approval_dms)}"
    
    async def reply(self, chat_id: str, text: str) -> None:
        """Record reply sent."""
        self.sent_messages.append({
            "to": chat_id,
            "text": text
        })


class TestPairingOwnerDM:
    """Test the pairing owner DM approval system."""
    
    def setup_method(self):
        """Set up test environment."""
        self.adapter = StubBotAdapter()
        self.pairing_store = PairingStore()
        self.config = BotConfig(
            unknown_user_policy="pair",
            owner_user_id="owner-123"
        )
        self.bot_context = BotContext(
            config=self.config,
            pairing_store=self.pairing_store,
            adapter=self.adapter
        )
    
    def create_test_message(self, user_id: str = "new-user", user_name: str = "Alice") -> BotMessage:
        """Create a test message from an unknown user."""
        message = BotMessage(
            message_id="msg-1",
            content="hello",
            message_type=MessageType.TEXT,
            sender=BotUser(
                user_id=user_id,
                username=user_name,
                display_name=user_name
            ),
            channel=BotChannel(
                channel_id="dm-123",
                channel_type="dm"
            ),
            timestamp=1234567890.0,
        )
        message._channel_type = "telegram"  # Add channel type for pairing
        return message
    
    async def test_unknown_user_triggers_pairing_request(self):
        """Test that unknown user triggers pairing request to owner."""
        message = self.create_test_message()
        
        # Handle unknown user message
        result = await UnknownUserHandler.handle(message, self.bot_context)
        
        # Should not allow message through
        assert result is False
        
        # Should send approval DM to owner
        assert len(self.adapter.approval_dms) == 1
        approval_dm = self.adapter.approval_dms[0]
        assert approval_dm["to"] == "owner-123"
        assert approval_dm["user_name"] == "Alice"
        assert approval_dm["channel"] == "dm-123"
        assert approval_dm["user_id"] == "new-user"
        
        # Should notify user that request was sent
        assert len(self.adapter.sent_messages) == 1
        assert self.adapter.sent_messages[0]["to"] == "dm-123"
        assert "sent to the owner for approval" in self.adapter.sent_messages[0]["text"]
    
    async def test_owner_approval_allows_future_messages(self):
        """Test that owner approval allows future messages from user."""
        # First message triggers pairing
        message = self.create_test_message()
        await UnknownUserHandler.handle(message, self.bot_context)
        
        # Get the pairing code that was generated
        approval_dm = self.adapter.approval_dms[0]
        code = approval_dm["code"]
        
        # Simulate owner approval using real signed callback
        keyboard = PairingUIBuilder.create_telegram_keyboard(
            user_name="Alice",
            code=code,
            channel="telegram",
            user_id="new-user",
        )
        callback_data = keyboard["inline_keyboard"][0][0]["callback_data"]  # Get approve button callback
        
        callback_handler = PairingCallbackHandler(self.pairing_store)
        result = await callback_handler.handle_approval_callback(
            callback_data=callback_data,
            owner_user_id="owner-123",
            bot_adapter=self.adapter,
        )
        assert result.success
        
        # Now a second message from the same user should be allowed
        message2 = self.create_test_message()
        result = await UnknownUserHandler.handle(message2, self.bot_context)
        
        # Should allow message through this time
        assert result is True
        
        # Should not send another approval DM
        assert len(self.adapter.approval_dms) == 1  # Still only the original one
    
    async def test_no_owner_id_falls_back_to_cli(self):
        """Test fallback to CLI instructions when owner_user_id is not configured."""
        # Configure bot without owner ID
        config = BotConfig(unknown_user_policy="pair")  # No owner_user_id set
        bot_context = BotContext(
            config=config,
            pairing_store=self.pairing_store,
            adapter=self.adapter
        )
        
        message = self.create_test_message()
        result = await UnknownUserHandler.handle(message, bot_context)
        
        # Should not allow message through
        assert result is False
        
        # Should not send approval DM (no owner configured)
        assert len(self.adapter.approval_dms) == 0
        
        # Should send CLI fallback instruction to user
        assert len(self.adapter.sent_messages) == 1
        sent_msg = self.adapter.sent_messages[0]
        assert sent_msg["to"] == "dm-123"
        assert "pairing code:" in sent_msg["text"]
        assert "praisonai pairing approve" in sent_msg["text"]
    
    async def test_policy_deny_silently_drops(self):
        """Test that policy 'deny' silently drops unknown users."""
        config = BotConfig(unknown_user_policy="deny")
        bot_context = BotContext(
            config=config,
            pairing_store=self.pairing_store,
            adapter=self.adapter
        )
        
        message = self.create_test_message()
        result = await UnknownUserHandler.handle(message, bot_context)
        
        # Should not allow message through
        assert result is False
        
        # Should not send any messages
        assert len(self.adapter.approval_dms) == 0
        assert len(self.adapter.sent_messages) == 0
    
    async def test_policy_allow_auto_approves(self):
        """Test that policy 'allow' auto-approves unknown users."""
        config = BotConfig(unknown_user_policy="allow")
        bot_context = BotContext(
            config=config,
            pairing_store=self.pairing_store,
            adapter=self.adapter
        )
        
        message = self.create_test_message()
        result = await UnknownUserHandler.handle(message, bot_context)
        
        # Should allow message through
        assert result is True
        
        # Should not send approval DM or messages
        assert len(self.adapter.approval_dms) == 0
        assert len(self.adapter.sent_messages) == 0
        
        # User should be paired automatically
        assert self.pairing_store.is_paired("new-user", "telegram")
    
    async def test_real_agentic_flow_with_stub_adapter(self):
        """Real agentic test - full flow with stub adapter."""
        from praisonaiagents import Agent
        
        # Create agent
        agent = Agent(
            name="test_assistant", 
            instructions="You are a helpful assistant. Respond with exactly: 'Hello! I can help you.'"
        )
        
        # Test the pairing flow
        message = self.create_test_message()
        result = await UnknownUserHandler.handle(message, self.bot_context)
        
        # Verify pairing request was sent
        assert result is False
        assert len(self.adapter.approval_dms) == 1
        
        approval_dm = self.adapter.approval_dms[0]
        assert "Alice" in approval_dm["user_name"]
        print(f"Approval DM sent to owner: {approval_dm}")
        
        # Manually approve the user (simulating owner approval)
        code = approval_dm["code"]
        self.pairing_store.verify_and_pair(
            code=code,
            channel_id="new-user",
            channel_type="telegram",
            label="Test approved"
        )
        
        # Now simulate the agent responding to the approved user
        response = agent.start("Say hello in one sentence")
        print(f"Agent response: {response}")
        
        # Verify we got a real LLM response
        assert isinstance(response, str)
        assert len(response) > 10  # Should be a real response, not empty
        assert "hello" in response.lower() or "hi" in response.lower()


if __name__ == "__main__":
    # Run the real agentic test
    import asyncio
    
    test = TestPairingOwnerDM()
    test.setup_method()
    
    async def run_test():
        await test.test_real_agentic_flow_with_stub_adapter()
    
    asyncio.run(run_test())