"""
Tests for Issue #2855: wire ``unknown_user_policy`` / ``owner_user_id`` from
gateway.yaml and emit a deny-aware startup warning for an empty allowlist.

Before this fix:
  * ``unknown_user_policy`` was never read from channel YAML, so an empty
    ``allowed_users`` always fell back to the default ``deny`` — silently
    dropping inbound DMs from unknown users.
  * The startup warning claimed the bot "accepts messages from everyone" even
    though the default policy dropped those messages.
"""

import logging

import pytest
from unittest.mock import patch

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig
from praisonai_bot.gateway.server import WebSocketGateway


def create_test_gateway_with_agent() -> WebSocketGateway:
    gateway = WebSocketGateway(host="127.0.0.1", port=8899)
    gateway._agents["default"] = Agent(name="test_agent", instructions="Test")
    return gateway


async def _capture_config(gateway, channels_config):
    captured = {}

    def mock_create_bot(channel_type, token, agent, config, ch_cfg):
        captured[channel_type] = config
        return None

    with patch.object(gateway, "_create_bot", side_effect=mock_create_bot):
        await gateway.start_channels(channels_config)
    return captured


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["allow", "pair", "deny"])
async def test_unknown_user_policy_wired_from_yaml(policy):
    """unknown_user_policy in gateway.yaml must reach BotConfig."""
    channels_config = {
        "telegram": {
            "token": "test-token",
            "unknown_user_policy": policy,
        }
    }
    gateway = create_test_gateway_with_agent()
    captured = await _capture_config(gateway, channels_config)
    assert captured["telegram"].unknown_user_policy == policy


@pytest.mark.asyncio
async def test_unknown_user_policy_defaults_to_deny_when_omitted():
    """Omitting the key preserves the secure default (deny)."""
    channels_config = {"telegram": {"token": "test-token"}}
    gateway = create_test_gateway_with_agent()
    captured = await _capture_config(gateway, channels_config)
    assert captured["telegram"].unknown_user_policy == "deny"


@pytest.mark.asyncio
async def test_owner_user_id_wired_from_yaml():
    """owner_user_id in gateway.yaml must reach BotConfig (trimmed)."""
    channels_config = {
        "telegram": {
            "token": "test-token",
            "owner_user_id": "  987654321  ",
        }
    }
    gateway = create_test_gateway_with_agent()
    captured = await _capture_config(gateway, channels_config)
    assert captured["telegram"].owner_user_id == "987654321"


@pytest.mark.asyncio
async def test_empty_allowlist_deny_warns_about_silent_drop(caplog):
    """Empty allowlist + deny must warn that unknown DMs are SILENTLY DROPPED."""
    channels_config = {"telegram": {"token": "test-token"}}
    gateway = create_test_gateway_with_agent()
    with caplog.at_level(logging.WARNING):
        await _capture_config(gateway, channels_config)
    text = caplog.text
    assert "SILENTLY DROPPED" in text
    assert "unknown_user_policy=deny" in text
    assert "accepts messages from everyone" not in text


@pytest.mark.asyncio
async def test_empty_allowlist_allow_warns_accepts_everyone(caplog):
    """Empty allowlist + allow retains the accurate 'accepts everyone' text."""
    channels_config = {
        "telegram": {"token": "test-token", "unknown_user_policy": "allow"}
    }
    gateway = create_test_gateway_with_agent()
    with caplog.at_level(logging.WARNING):
        await _capture_config(gateway, channels_config)
    text = caplog.text
    assert "accepts messages from everyone" in text
    assert "SILENTLY DROPPED" not in text


def test_is_explicitly_allowed_semantics():
    """Empty allowlist is NOT explicitly allowed; populated list gates by id."""
    empty = BotConfig(token="x", allowed_users=[])
    assert empty.is_explicitly_allowed("u1") is False
    # Backward compat: is_user_allowed still returns True for empty lists.
    assert empty.is_user_allowed("u1") is True

    scoped = BotConfig(token="x", allowed_users=["u1"])
    assert scoped.is_explicitly_allowed("u1") is True
    assert scoped.is_explicitly_allowed("u2") is False


if __name__ == "__main__":
    pytest.main([__file__])
