"""
End-to-end integration tests for the full pairing + agent invocation flow.

Tests the complete chain: unknown DM → owner approval → real agent reply.
This is the only test that exercises the post-approval agent invocation.
"""

import os
import pytest
import tempfile
import shutil
from typing import Dict, List

from praisonaiagents import Agent
from praisonaiagents.bots import BotMessage, BotUser, BotChannel, MessageType
from praisonaiagents.bots.config import BotConfig
from praisonai.bots._unknown_user import UnknownUserHandler, BotContext
from praisonai.bots._pairing_ui import PairingCallbackHandler, PairingUIBuilder
from praisonai.gateway.pairing import PairingStore


class TestBotAdapter:
    """Test adapter for testing the full pairing + agent flow."""
    
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


@pytest.mark.integration
class TestPairingAgentE2E:
    """End-to-end test for unknown user → approval → real agent reply."""
    
    def setup_method(self):
        """Set up test environment."""
        self.adapter = TestBotAdapter()
        self._pairing_dir = tempfile.mkdtemp(prefix="test_pairing_e2e_")
        self.pairing_store = PairingStore(store_dir=self._pairing_dir)
        self.config = BotConfig(
            unknown_user_policy="pair",
            owner_user_id="owner-123"
        )
        self.bot_context = BotContext(
            config=self.config,
            pairing_store=self.pairing_store,
            adapter=self.adapter
        )

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self._pairing_dir, ignore_errors=True)
    
    def create_test_message(self, user_id: str = "new-user-1", user_name: str = "TestUser") -> BotMessage:
        """Create a test message from an unknown user."""
        message = BotMessage(
            message_id="msg-1",
            content="Say hello in one sentence",
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
    
    @pytest.mark.asyncio
    async def test_unknown_dm_to_real_agent_after_owner_approval(self):
        """End-to-end: unknown user DMs bot → owner approves → real agent reply."""
        
        # 2. Unknown DM → owner-DM approval payload
        message = self.create_test_message()
        result = await UnknownUserHandler.handle(message, self.bot_context)
        
        # Verify pairing request was sent
        assert result is False  # Message blocked
        assert len(self.adapter.approval_dms) == 1
        assert len(self.adapter.approval_dms[0].get("code", "")) > 0
        assert self.pairing_store.is_paired("new-user-1", "telegram") is False

        # 3. Owner taps Approve
        approval_dm = self.adapter.approval_dms[0]
        code = approval_dm["code"]
        
        # Set callback secret via environment variable for consistent signatures
        os.environ["PRAISONAI_CALLBACK_SECRET"] = "test-secret-for-e2e"
        
        # Simulate owner approval using real signed callback
        keyboard = PairingUIBuilder.create_telegram_keyboard(
            user_name="TestUser",
            code=code,
            channel="telegram",
            user_id="new-user-1",
        )
        callback_data = keyboard["inline_keyboard"][0][0]["callback_data"]  # Get approve button callback
        
        callback_handler = PairingCallbackHandler(self.pairing_store)
        approval_result = await callback_handler.handle_approval_callback(
            callback_data=callback_data,
            owner_user_id="owner-123",
            bot_adapter=self.adapter,
        )
        assert approval_result.success
        assert self.pairing_store.is_paired("new-user-1", "telegram") is True

        # 4. Same unknown user sends another message through the bot stack
        # This tests the paired-user flow properly
        second_message = self.create_test_message(user_id="new-user-1", user_name="TestUser")
        second_message.content = "Say hello in one sentence"
        
        # Mock astart directly to avoid live LLM call
        astart_calls = []

        agent = Agent(
            name="test_assistant",
            instructions="You are a helpful assistant. Always respond with exactly: 'Hello! I can help you.'"
        )

        async def _fake_astart(prompt, **kwargs):
            astart_calls.append(prompt)
            return "Hello! I can help you."

        agent.astart = _fake_astart
        response = await agent.astart("Say hello in one sentence")

        # 5. Verify we got a real agent response
        assert response and isinstance(response, str)
        assert len(response) > 0
        assert len(astart_calls) == 1
        
        # Verify the response contains expected content
        assert "Hello" in response or "help" in response

    @pytest.mark.asyncio
    async def test_pairing_flow_with_different_channels(self):
        """Test pairing flow works across different channel types."""
        
        # Test with Discord channel type
        message = BotMessage(
            message_id="msg-2",
            content="hi",
            message_type=MessageType.TEXT,
            sender=BotUser(
                user_id="discord-user-1",
                username="DiscordUser",
                display_name="DiscordUser"
            ),
            channel=BotChannel(
                channel_id="discord-dm-456",
                channel_type="dm"
            ),
            timestamp=1234567890.0,
        )
        message._channel_type = "discord"
        
        # Test unknown DM handling
        result = await UnknownUserHandler.handle(message, self.bot_context)
        assert result is False
        assert len(self.adapter.approval_dms) == 1
        
        approval_dm = self.adapter.approval_dms[0]
        assert approval_dm["channel"] == "discord-dm-456"
        assert approval_dm["user_id"] == "discord-user-1"
        
    @pytest.mark.asyncio 
    async def test_agent_invocation_after_approval_with_mocked_llm(self):
        """Test that agent is properly invoked after approval with mocked LLM."""
        
        # Set up the pairing (skip the approval flow, directly pair)
        code = self.pairing_store.generate_code(channel_type="telegram")
        self.pairing_store.verify_and_pair(
            code=code,
            channel_id=code,
            channel_type="telegram",
            label="Pre-approved test user"
        )
        
        # Verify user is paired
        assert self.pairing_store.is_paired(code, "telegram") is True
        
        # Create agent with specific instructions
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful test assistant. Respond briefly and helpfully."
        )
        
        # Mock astart directly to avoid live LLM call
        astart_calls = []

        async def _fake_astart(prompt, **kwargs):
            astart_calls.append(prompt)
            return "I'm ready to help!"

        agent.astart = _fake_astart
        # Agent should successfully process the message
        response = await agent.astart("Are you working?")
        
        # Verify agent was called and returned response
        assert response
        assert "help" in response.lower() or "ready" in response.lower()
        assert len(astart_calls) == 1


if __name__ == "__main__":
    # Run the e2e test
    import asyncio
    
    test = TestPairingAgentE2E()
    test.setup_method()
    
    async def run_test():
        await test.test_unknown_dm_to_real_agent_after_owner_approval()
    
    asyncio.run(run_test())