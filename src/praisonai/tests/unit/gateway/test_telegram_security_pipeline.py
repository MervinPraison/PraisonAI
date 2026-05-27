"""
Test that Telegram gateway polling path enforces security checks.

This test verifies the fix for issue #1747 where gateway Telegram polling
bypassed allowed_users, pairing, and group policy enforcement.

The fix introduces a shared security pipeline `process_inbound_telegram_message()`
used by both standalone and gateway paths to ensure identical security enforcement.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
from typing import Dict, Any

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig, BotMessage, BotUser, BotChannel, MessageType
from praisonai.bots.telegram import TelegramBot, process_inbound_telegram_message
from praisonai.bots._unknown_user import BotContext, UnknownUserHandler
from praisonai.gateway.pairing import PairingStore


def create_mock_telegram_update(user_id: str = "12345", chat_id: str = "-100123456789", text: str = "test message", chat_type: str = "group"):
    """Create a mock Telegram Update for testing."""
    update = MagicMock()
    
    # Mock message
    update.message = MagicMock()
    update.message.text = text
    update.message.voice = None
    update.message.audio = None
    update.message.date.timestamp.return_value = 1234567890.0
    update.message.message_id = 123
    update.message.message_thread_id = None
    
    # Mock user
    update.message.from_user = MagicMock()
    update.message.from_user.id = int(user_id)
    update.message.from_user.username = f"user_{user_id}"
    update.message.from_user.first_name = f"User {user_id}"
    update.message.from_user.is_bot = False
    
    # Mock chat
    update.message.chat = MagicMock()
    update.message.chat.id = int(chat_id)
    update.message.chat.type = chat_type
    update.message.chat.title = "Test Group" if chat_type == "group" else None
    update.message.chat.username = f"chat_{chat_id}"
    
    return update


def create_test_bot(allowed_users=None, allowed_channels=None, group_policy="mention_only") -> TelegramBot:
    """Create a TelegramBot for testing with specified security config."""
    config = BotConfig(
        token="test_token",
        allowed_users=allowed_users or [],
        allowed_channels=allowed_channels or [],
        group_policy=group_policy,
    )
    
    bot = TelegramBot(token="test_token", config=config)
    
    # Mock required attributes
    bot._bot_user = BotUser(
        user_id="123456789",
        username="test_bot",
        display_name="Test Bot",
        is_bot=True,
    )
    
    # Mock the fire_message_received method
    bot.fire_message_received = MagicMock()
    
    return bot


@pytest.mark.asyncio 
async def test_user_allowlist_enforcement():
    """Test that user allowlist is enforced in the security pipeline."""
    
    # Bot with restricted user allowlist
    bot = create_test_bot(allowed_users=["42"])
    
    # Message from allowed user
    allowed_update = create_mock_telegram_update(user_id="42", text="hello")
    allowed_message = await process_inbound_telegram_message(allowed_update, bot)
    assert allowed_message is not None, "Message from allowed user should pass"
    assert allowed_message.sender.user_id == "42"
    
    # Message from disallowed user
    disallowed_update = create_mock_telegram_update(user_id="99", text="hello")
    disallowed_message = await process_inbound_telegram_message(disallowed_update, bot)
    assert disallowed_message is None, "Message from disallowed user should be blocked"


@pytest.mark.asyncio
async def test_channel_allowlist_enforcement():
    """Test that channel allowlist is enforced in the security pipeline."""
    
    # Bot with restricted channel allowlist
    bot = create_test_bot(allowed_channels=["-100123456789"])
    
    # Message from allowed channel
    allowed_update = create_mock_telegram_update(chat_id="-100123456789", text="hello")
    allowed_message = await process_inbound_telegram_message(allowed_update, bot)
    assert allowed_message is not None, "Message from allowed channel should pass"
    assert allowed_message.channel.channel_id == "-100123456789"
    
    # Message from disallowed channel
    disallowed_update = create_mock_telegram_update(chat_id="-100999999999", text="hello")
    disallowed_message = await process_inbound_telegram_message(disallowed_update, bot)
    assert disallowed_message is None, "Message from disallowed channel should be blocked"


@pytest.mark.asyncio
async def test_group_policy_mention_enforcement():
    """Test that group mention policy is enforced in the security pipeline."""
    
    # Bot with mention_only group policy
    bot = create_test_bot(group_policy="mention_only")
    
    # Group message with bot mention - should pass
    mention_update = create_mock_telegram_update(
        chat_type="group", 
        text="@test_bot please help"
    )
    mention_message = await process_inbound_telegram_message(mention_update, bot)
    assert mention_message is not None, "Group message with mention should pass"
    
    # Group message without mention - should be blocked
    no_mention_update = create_mock_telegram_update(
        chat_type="group", 
        text="hello everyone"
    )
    no_mention_message = await process_inbound_telegram_message(no_mention_update, bot)
    assert no_mention_message is None, "Group message without mention should be blocked"
    
    # Commands should always pass regardless of mention
    command_update = create_mock_telegram_update(
        chat_type="group", 
        text="/help"
    )
    command_message = await process_inbound_telegram_message(command_update, bot)
    assert command_message is not None, "Commands should always pass in groups"


@pytest.mark.asyncio
async def test_dm_messages_bypass_group_policies():
    """Test that DM messages bypass group-specific policies."""
    
    # Bot with mention_only group policy
    bot = create_test_bot(group_policy="mention_only")
    
    # DM message without mention - should pass
    dm_update = create_mock_telegram_update(
        chat_type="private", 
        text="hello bot"
    )
    dm_message = await process_inbound_telegram_message(dm_update, bot)
    assert dm_message is not None, "DM messages should bypass group mention requirements"


@pytest.mark.asyncio
@patch.object(UnknownUserHandler, 'handle')
async def test_pairing_system_integration(mock_unknown_handler):
    """Test that pairing system is properly integrated."""
    
    # Mock the UnknownUserHandler to simulate pairing rejection
    mock_unknown_handler.return_value = False  # User not approved
    
    # Bot with empty allowlist (no users explicitly allowed)
    bot = create_test_bot(allowed_users=[])
    
    # Message from unknown user
    unknown_update = create_mock_telegram_update(user_id="12345", text="hello")
    unknown_message = await process_inbound_telegram_message(unknown_update, bot)
    
    # Should be blocked by pairing system
    assert unknown_message is None, "Unknown user should be blocked by pairing system"
    
    # Verify UnknownUserHandler.handle was called
    mock_unknown_handler.assert_called_once()


@pytest.mark.asyncio
async def test_empty_allowlists_allow_all():
    """Test that empty allowlists allow all users/channels (default behavior)."""
    
    # Bot with no restrictions
    bot = create_test_bot(allowed_users=[], allowed_channels=[])
    
    # Message from any user in any channel
    update = create_mock_telegram_update(user_id="99999", chat_id="-999999999", text="hello")
    message = await process_inbound_telegram_message(update, bot)
    assert message is not None, "Empty allowlists should allow all users and channels"


@pytest.mark.asyncio
async def test_audio_message_transcription():
    """Test that audio messages are properly transcribed in the security pipeline."""
    
    bot = create_test_bot()
    
    # Mock the transcribe_audio method
    bot._transcribe_audio = AsyncMock(return_value="[Voice message]: transcribed text")
    
    # Create update with voice message
    update = create_mock_telegram_update(text=None)
    update.message.text = None
    update.message.voice = MagicMock()  # Simulate voice message
    
    message = await process_inbound_telegram_message(update, bot)
    
    assert message is not None, "Voice message should be processed"
    assert message.content == "[Voice message]: transcribed text"
    bot._transcribe_audio.assert_called_once()


def test_security_pipeline_exists():
    """Basic smoke test to ensure the security pipeline function exists and is importable."""
    from praisonai.bots.telegram import process_inbound_telegram_message
    assert callable(process_inbound_telegram_message), "Security pipeline function should be callable"


@pytest.mark.asyncio
async def test_shared_pipeline_consistency():
    """Test that the shared pipeline provides consistent results."""
    
    # Create identical bot configs
    bot1 = create_test_bot(allowed_users=["42"], group_policy="mention_only")
    bot2 = create_test_bot(allowed_users=["42"], group_policy="mention_only")
    
    # Same message update
    update = create_mock_telegram_update(user_id="42", text="@test_bot hello")
    
    # Both should produce identical results
    message1 = await process_inbound_telegram_message(update, bot1)
    message2 = await process_inbound_telegram_message(update, bot2)
    
    assert message1 is not None and message2 is not None
    assert message1.content == message2.content
    assert message1.sender.user_id == message2.sender.user_id