"""
Tests for the UnknownUserHandler functionality.

Tests the unknown-user policies (deny/allow/pair) and the pairing-approval
flow against the canonical handler in ``praisonai.bots._unknown_user``.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from praisonaiagents.bots import BotConfig, BotMessage, BotUser, BotChannel
from praisonai.gateway.pairing import PairingStore
from praisonai.bots._unknown_user import UnknownUserHandler, BotContext


def make_message(
    user_id: str = "unknown_user",
    channel_id: str = "test_chat",
    channel_type: str = "telegram",
    username: str = "testuser",
) -> BotMessage:
    """Create a test message from an unknown user."""
    message = BotMessage(
        sender=BotUser(user_id=user_id, username=username),
        channel=BotChannel(channel_id=channel_id, channel_type=channel_type),
    )
    message._channel_type = channel_type
    return message


@pytest.mark.asyncio
async def test_unknown_user_handler_deny_policy():
    """Deny policy silently drops unknown users."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="deny")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    bot_ctx = BotContext(config=config, pairing_store=mock_store)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False


@pytest.mark.asyncio
async def test_unknown_user_handler_allow_policy():
    """Allow policy lets unknown users through without pairing."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="allow")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    bot_ctx = BotContext(config=config, pairing_store=mock_store)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is True


@pytest.mark.asyncio
async def test_already_paired_user_allowed():
    """Already-paired users are allowed regardless of policy."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="deny")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = True
    bot_ctx = BotContext(config=config, pairing_store=mock_store)

    message = make_message(user_id="paired_user")
    result = await UnknownUserHandler.handle(message, bot_ctx)

    assert result is True
    mock_store.is_paired.assert_called_once_with("paired_user", "telegram")


@pytest.mark.asyncio
async def test_pairing_flow_not_paired_cli_fallback():
    """Pairing policy without an owner generates a code and replies with CLI instructions."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "ABCD1234"

    adapter = Mock()
    adapter.reply = AsyncMock()
    bot_ctx = BotContext(config=config, pairing_store=mock_store, adapter=adapter)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False  # Dropped until approved
    mock_store.generate_code.assert_called_once_with(channel_type="telegram")
    adapter.reply.assert_awaited_once()

    sent_text = adapter.reply.call_args[0][1]
    assert "ABCD1234" in sent_text
    assert "praisonai pairing approve telegram ABCD1234" in sent_text


@pytest.mark.asyncio
async def test_pairing_flow_sends_owner_approval_dm():
    """Pairing policy with an owner sends an approval DM to the owner."""
    config = BotConfig(
        allowed_users=["allowed_user"],
        unknown_user_policy="pair",
        owner_user_id="owner-123",
    )
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "ABCD1234"

    adapter = Mock()
    adapter.reply = AsyncMock()
    adapter.send_approval_dm = AsyncMock(return_value="msg_1")
    bot_ctx = BotContext(config=config, pairing_store=mock_store, adapter=adapter)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False
    adapter.send_approval_dm.assert_awaited_once()
    kwargs = adapter.send_approval_dm.call_args.kwargs
    assert kwargs["owner_user_id"] == "owner-123"
    assert kwargs["user_name"] == "testuser"
    assert kwargs["user_id"] == "unknown_user"
    assert kwargs["code"] == "ABCD1234"
    assert kwargs["channel"] == "telegram"

    # User is notified the request was sent to the owner.
    adapter.reply.assert_awaited_once()
    assert "approval" in adapter.reply.call_args[0][1].lower()


@pytest.mark.asyncio
async def test_pairing_owner_dm_failure_falls_back_to_cli():
    """When the owner approval DM cannot be delivered, fall back to CLI instructions."""
    config = BotConfig(
        allowed_users=["allowed_user"],
        unknown_user_policy="pair",
        owner_user_id="owner-123",
    )
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "ABCD1234"

    adapter = Mock()
    adapter.reply = AsyncMock()
    adapter.send_approval_dm = AsyncMock(return_value=None)
    bot_ctx = BotContext(config=config, pairing_store=mock_store, adapter=adapter)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False
    adapter.send_approval_dm.assert_awaited_once()
    adapter.reply.assert_awaited_once()
    assert "praisonai pairing approve telegram ABCD1234" in adapter.reply.call_args[0][1]


@pytest.mark.asyncio
async def test_pairing_owner_dm_exception_falls_back_to_cli():
    """When the owner approval DM raises, fall back to CLI instructions."""
    config = BotConfig(
        allowed_users=["allowed_user"],
        unknown_user_policy="pair",
        owner_user_id="owner-123",
    )
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.return_value = "ABCD1234"

    adapter = Mock()
    adapter.reply = AsyncMock()
    adapter.send_approval_dm = AsyncMock(side_effect=RuntimeError("DM failed"))
    bot_ctx = BotContext(config=config, pairing_store=mock_store, adapter=adapter)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False
    adapter.send_approval_dm.assert_awaited_once()
    adapter.reply.assert_awaited_once()
    assert "praisonai pairing approve telegram ABCD1234" in adapter.reply.call_args[0][1]


@pytest.mark.asyncio
async def test_pairing_store_code_generation_failure():
    """A failure generating a pairing code drops the message gracefully."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="pair")
    mock_store = Mock(spec=PairingStore)
    mock_store.is_paired.return_value = False
    mock_store.generate_code.side_effect = RuntimeError("Store busy")

    adapter = Mock()
    adapter.reply = AsyncMock()
    bot_ctx = BotContext(config=config, pairing_store=mock_store, adapter=adapter)

    result = await UnknownUserHandler.handle(make_message(), bot_ctx)

    assert result is False
    adapter.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_without_sender_dropped():
    """A message with no sender is dropped."""
    config = BotConfig(allowed_users=["allowed_user"], unknown_user_policy="allow")
    bot_ctx = BotContext(config=config, pairing_store=Mock(spec=PairingStore))

    message = BotMessage(
        sender=None,
        channel=BotChannel(channel_id="test_chat", channel_type="telegram"),
    )

    result = await UnknownUserHandler.handle(message, bot_ctx)

    assert result is False


@pytest.mark.asyncio
async def test_invalid_policy_rejected_at_config():
    """Invalid policy is rejected at BotConfig construction."""
    with pytest.raises(ValueError, match="unknown_user_policy must be one of"):
        BotConfig(allowed_users=["allowed_user"], unknown_user_policy="invalid_policy")


if __name__ == "__main__":
    pytest.main([__file__])
