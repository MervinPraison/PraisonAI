"""Tests for credential-presence channel auto-enablement (Issue #4779).

The gateway config schema auto-registers a channel for any known platform
whose credential env var(s) are present, when the user has neither declared
nor explicitly disabled that channel — so ``export TELEGRAM_BOT_TOKEN=... &&
praisonai gateway`` brings up a working bot with no ``channels:`` block.
"""

import pytest

from praisonai_bot.bots._config_schema import GatewayConfigSchema
from praisonai_bot.bots import _registry as R


# Every built-in credential env var, cleared before each test so a stray
# value in the runner environment never auto-enables an unexpected channel.
_CRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
]


@pytest.fixture(autouse=True)
def _clear_credentials(monkeypatch):
    for var in _CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


def _agents():
    return {"assistant": {"instructions": "You are a helpful assistant"}}


def test_credential_env_source_of_truth():
    """Built-in platforms self-describe their credential env var(s)."""
    assert R.get_platform_credential_env("telegram") == ("TELEGRAM_BOT_TOKEN",)
    assert R.get_platform_credential_env("slack") == (
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
    )
    # An unknown/no-credential platform returns an empty tuple.
    assert R.get_platform_credential_env("nope") == ()


def test_autoenable_telegram_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    cfg = GatewayConfigSchema(agents=_agents())
    assert "telegram" in cfg.channels
    ch = cfg.channels["telegram"]
    assert ch.platform == "telegram"
    # Resolved via the ${ENV} interpolation to the present token.
    assert ch.token == "123:abc"
    assert ch.routes == {
        "dm": "assistant",
        "group": "assistant",
        "default": "assistant",
    }


def test_autoenable_multiple_credentials_fan_out(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "d")
    cfg = GatewayConfigSchema(agents=_agents())
    assert {"telegram", "discord"} <= set(cfg.channels)


def test_explicit_channel_wins(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
    cfg = GatewayConfigSchema(
        agents=_agents(),
        channels={
            "telegram": {
                "platform": "telegram",
                "token": "explicit-token",
                "routes": {"default": "assistant"},
            }
        },
    )
    # The user's explicit token is untouched by auto-enable.
    assert cfg.channels["telegram"].token == "explicit-token"


def test_explicit_disable_opts_out(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "d")
    cfg = GatewayConfigSchema(
        agents=_agents(),
        channels={
            "telegram": {"platform": "telegram", "enabled": False, "token": "t"}
        },
    )
    # Explicit opt-out wins even though the token is present…
    assert "telegram" not in cfg.channels
    # …but other present credentials still fan out.
    assert "discord" in cfg.channels


def test_auto_enable_disabled_restores_strict_guard(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    with pytest.raises(ValueError, match="No channels configured"):
        GatewayConfigSchema(agents=_agents(), auto_enable_from_env=False)


def test_partial_credentials_do_not_autoenable(monkeypatch):
    # Slack needs BOTH the bot token and the app token.
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb")
    with pytest.raises(ValueError, match="No channels configured"):
        GatewayConfigSchema(agents=_agents())
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp")
    cfg = GatewayConfigSchema(agents=_agents())
    assert "slack" in cfg.channels


def test_default_agent_prefers_routing_default(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    cfg = GatewayConfigSchema(
        agents={"support": {"instructions": "x"}, "sales": {"instructions": "y"}},
        routing={"default": "sales"},
    )
    assert cfg.channels["telegram"].routes["default"] == "sales"


def test_no_credentials_still_fails_closed(monkeypatch):
    with pytest.raises(ValueError, match="No channels configured"):
        GatewayConfigSchema(agents=_agents())
