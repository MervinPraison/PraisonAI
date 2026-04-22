"""
Tests for the UnknownUserHandler functionality.

Tests the pairing flow, rate limiting, and different policies.
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass
from typing import Optional

from praisonaiagents.bots import BotConfig, BotMessage, BotUser, BotChannel
from praisonai.gateway.pairing import PairingStore, PairedChannel
from praisonai.bots._auth import UnknownUserHandler


@pytest.fixture
def bot_config():
    """Create a test bot config."""
    return BotConfig(
        token="test-token",
        allowed_users=["allowed_user_123"],
        unknown_user_policy="deny"
    )


@pytest.fixture 
def pairing_config():
    """Create a bot config with pairing policy."""
    return BotConfig(
        token="test-token", 
        allowed_users=["allowed_user_123"],
        unknown_user_policy="pair"
    )


@pytest.fixture
def test_message():
    """Create a test message from unknown user."""
    return BotMessage(
        message_id="msg_123",
        content="Hello bot",
        sender=BotUser(user_id="unknown_user_456", username="testuser"),
        channel=BotChannel(channel_id="chat_789", channel_type="telegram")
    )


@pytest.fixture
def mock_pairing_store():
    """Create a mock pairing store."""
    store = Mock(spec=PairingStore)
    store.is_paired.return_value = False
    store.generate_code.return_value = "ABCD1234" 
    store.verify_and_pair.return_value = True
    return store


def test_unknown_user_handler_deny_policy():
    """Test unknown user handler with deny policy."""
    config = BotConfig(unknown_user_policy="deny")
    handler = UnknownUserHandler(config)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="test")
    )
    
    # Should drop unknown users
    result = pytest.helpers.run_async(handler.handle(message))
    assert result == "drop"


def test_unknown_user_handler_allow_policy():
    """Test unknown user handler with allow policy."""
    config = BotConfig(unknown_user_policy="allow")
    handler = UnknownUserHandler(config)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="test")
    )
    
    # Should allow unknown users
    result = pytest.helpers.run_async(handler.handle(message))
    assert result == "allow"


def test_unknown_user_handler_allowed_user():
    """Test that allowed users are always allowed."""
    config = BotConfig(
        allowed_users=["allowed_user_123"],
        unknown_user_policy="deny"
    )
    handler = UnknownUserHandler(config)
    
    message = BotMessage(
        sender=BotUser(user_id="allowed_user_123"),
        channel=BotChannel(channel_id="test_chat", channel_type="test")
    )
    
    # Should allow known users regardless of policy
    result = pytest.helpers.run_async(handler.handle(message))
    assert result == "allow"


@pytest.mark.asyncio
async def test_pairing_flow_not_paired():
    """Test pairing flow for unknown user not yet paired."""
    config = BotConfig(unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "ABCD1234"
    
    send_callback = AsyncMock()
    handler = UnknownUserHandler(config, mock_store, send_callback)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    result = await handler.handle(message)
    
    assert result == "drop"  # Should drop after sending pairing code
    mock_store.generate_code.assert_called_once_with(channel_type="telegram")
    send_callback.assert_called_once()
    
    # Check pairing instructions were sent
    sent_message = send_callback.call_args[0][1] 
    assert "ABCD1234" in sent_message
    assert "praisonai pairing approve telegram ABCD1234" in sent_message


@pytest.mark.asyncio
async def test_pairing_flow_already_paired():
    """Test pairing flow for user who is already paired."""
    config = BotConfig(unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = True  # Already paired
    
    handler = UnknownUserHandler(config, mock_store)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    result = await handler.handle(message)
    
    assert result == "allow"  # Should allow already paired users
    mock_store.is_paired.assert_called_once_with("unknown_user", "telegram")


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting prevents spam."""
    config = BotConfig(unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "CODE123"
    
    handler = UnknownUserHandler(config, mock_store)
    
    message = BotMessage(
        sender=BotUser(user_id="spam_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    # First request should generate code
    result1 = await handler.handle(message)
    assert result1 == "drop"
    assert mock_store.generate_code.call_count == 1
    
    # Second request immediately should be rate limited
    result2 = await handler.handle(message)
    assert result2 == "drop"
    assert mock_store.generate_code.call_count == 1  # No additional calls


def test_pairing_flow_no_store():
    """Test pairing policy without pairing store falls back to deny."""
    config = BotConfig(unknown_user_policy="pair")
    handler = UnknownUserHandler(config, pairing_store=None)  # No store
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    result = pytest.helpers.run_async(handler.handle(message))
    assert result == "drop"


@pytest.mark.asyncio
async def test_pairing_store_exception():
    """Test handling of pairing store exceptions."""
    config = BotConfig(unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.side_effect = Exception("Store error")
    
    handler = UnknownUserHandler(config, mock_store)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    # Should handle exception gracefully
    result = await handler.handle(message)
    assert result == "drop"


def test_invalid_policy_fallback():
    """Test that invalid policy falls back to deny."""
    config = BotConfig(unknown_user_policy="invalid_policy")
    handler = UnknownUserHandler(config)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    result = pytest.helpers.run_async(handler.handle(message))
    assert result == "drop"


@pytest.mark.asyncio
async def test_send_callback_failure():
    """Test handling of send callback failures."""
    config = BotConfig(unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "CODE123"
    
    # Failing send callback
    send_callback = AsyncMock(side_effect=Exception("Send failed"))
    handler = UnknownUserHandler(config, mock_store, send_callback)
    
    message = BotMessage(
        sender=BotUser(user_id="unknown_user"),
        channel=BotChannel(channel_id="test_chat", channel_type="telegram")
    )
    
    # Should handle send failure gracefully
    result = await handler.handle(message)
    assert result == "drop"
    
    # Code should still have been generated
    mock_store.generate_code.assert_called_once()


# Test helper for running async functions in sync tests
@pytest.fixture(scope="session", autouse=True)
def pytest_helpers():
    """Add helper functions to pytest."""
    import asyncio
    
    class Helpers:
        @staticmethod
        def run_async(coro):
            """Run async coroutine in sync test."""
            return asyncio.get_event_loop().run_until_complete(coro)
    
    pytest.helpers = Helpers()


if __name__ == "__main__":
    pytest.main([__file__])