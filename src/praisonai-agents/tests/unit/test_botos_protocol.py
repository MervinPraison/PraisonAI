"""
TDD tests for BotOS protocol, config, and exports.

Tests written FIRST — implementation follows.
"""

import pytest


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Core SDK Protocol & Config exports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestBotOSProtocolExists:
    """BotOSProtocol must be importable from core SDK."""

    def test_import_from_bots_protocols(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert BotOSProtocol is not None

    def test_import_from_bots_package(self):
        from praisonaiagents.bots import BotOSProtocol
        assert BotOSProtocol is not None

    def test_import_from_top_level(self):
        from praisonaiagents import BotOSProtocol
        assert BotOSProtocol is not None

    def test_is_runtime_checkable(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        # runtime_checkable protocols support isinstance checks
        assert hasattr(BotOSProtocol, '__protocol_attrs__') or hasattr(BotOSProtocol, '_is_runtime_protocol')

    def test_protocol_has_start(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert hasattr(BotOSProtocol, 'start')

    def test_protocol_has_stop(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert hasattr(BotOSProtocol, 'stop')

    def test_protocol_has_add_bot(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert hasattr(BotOSProtocol, 'add_bot')

    def test_protocol_has_list_bots(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert hasattr(BotOSProtocol, 'list_bots')

    def test_protocol_has_is_running(self):
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert 'is_running' in dir(BotOSProtocol)


class TestBotOSConfigExists:
    """BotOSConfig must be importable from core SDK."""

    def test_import_from_bots_config(self):
        from praisonaiagents.bots.config import BotOSConfig
        assert BotOSConfig is not None

    def test_import_from_bots_package(self):
        from praisonaiagents.bots import BotOSConfig
        assert BotOSConfig is not None

    def test_import_from_top_level(self):
        from praisonaiagents import BotOSConfig
        assert BotOSConfig is not None

    def test_default_values(self):
        from praisonaiagents.bots.config import BotOSConfig
        cfg = BotOSConfig()
        assert cfg.name == "PraisonAI BotOS"
        assert isinstance(cfg.platforms, dict)

    def test_to_dict(self):
        from praisonaiagents.bots.config import BotOSConfig
        cfg = BotOSConfig(name="test")
        d = cfg.to_dict()
        assert d["name"] == "test"
        assert "platforms" in d

    def test_platforms_dict(self):
        from praisonaiagents.bots.config import BotOSConfig
        cfg = BotOSConfig(platforms={"telegram": {"token": "abc"}})
        assert "telegram" in cfg.platforms


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Wrapper: Bot class
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestBotClass:
    """Bot is the user-facing single-platform wrapper."""

    def test_import_from_wrapper(self):
        from praisonai.bots import Bot
        assert Bot is not None

    def test_bot_requires_platform(self):
        from praisonai.bots import Bot
        with pytest.raises(TypeError):
            Bot()  # platform is required

    def test_bot_stores_platform(self):
        from praisonai.bots import Bot
        bot = Bot("telegram")
        assert bot.platform == "telegram"

    def test_bot_accepts_agent(self):
        from praisonai.bots import Bot
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.name = "test"
        bot = Bot("telegram", agent=agent)
        assert bot.agent is agent

    def test_bot_accepts_agent_team(self):
        """Bot should accept AgentTeam as agent."""
        from praisonai.bots import Bot
        from unittest.mock import MagicMock
        team = MagicMock()
        team.name = "team"
        bot = Bot("telegram", agent=team)
        assert bot.agent is team

    def test_bot_accepts_kwargs(self):
        """Platform-specific kwargs should pass through."""
        from praisonai.bots import Bot
        bot = Bot("whatsapp", mode="web", phone_number_id="123")
        assert bot._kwargs.get("mode") == "web"
        assert bot._kwargs.get("phone_number_id") == "123"

    def test_bot_token_from_env(self):
        """Bot resolves token from env var convention."""
        import os
        from praisonai.bots import Bot
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token-123"
        try:
            bot = Bot("telegram")
            assert bot.token == "test-token-123"
        finally:
            del os.environ["TELEGRAM_BOT_TOKEN"]

    def test_bot_explicit_token(self):
        from praisonai.bots import Bot
        bot = Bot("telegram", token="explicit-token")
        assert bot.token == "explicit-token"

    def test_bot_not_running_initially(self):
        from praisonai.bots import Bot
        bot = Bot("telegram")
        assert bot.is_running is False

    def test_bot_unknown_platform(self):
        """Unknown platform should raise ValueError on start, not init."""
        from praisonai.bots import Bot
        bot = Bot("unknown_platform")
        assert bot.platform == "unknown_platform"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Wrapper: BotOS class
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestBotOSClass:
    """BotOS is the multi-platform orchestrator."""

    def test_import_from_wrapper(self):
        from praisonai.bots import BotOS
        assert BotOS is not None

    def test_botos_empty_init(self):
        from praisonai.bots import BotOS
        botos = BotOS()
        assert botos.is_running is False

    def test_botos_with_bots_list(self):
        from praisonai.bots import BotOS, Bot
        bot1 = Bot("telegram")
        bot2 = Bot("discord")
        botos = BotOS(bots=[bot1, bot2])
        assert len(botos.list_bots()) == 2

    def test_botos_add_bot(self):
        from praisonai.bots import BotOS, Bot
        botos = BotOS()
        bot = Bot("telegram")
        botos.add_bot(bot)
        assert len(botos.list_bots()) == 1

    def test_botos_shortcut_agent_plus_platforms(self):
        """BotOS(agent=..., platforms=[...]) convenience."""
        from praisonai.bots import BotOS
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.name = "test"
        botos = BotOS(agent=agent, platforms=["telegram", "discord"])
        assert len(botos.list_bots()) == 2

    def test_botos_list_bots_returns_platform_names(self):
        from praisonai.bots import BotOS, Bot
        botos = BotOS(bots=[Bot("telegram"), Bot("slack")])
        names = botos.list_bots()
        assert "telegram" in names
        assert "slack" in names

    def test_botos_get_bot(self):
        from praisonai.bots import BotOS, Bot
        bot = Bot("telegram")
        botos = BotOS(bots=[bot])
        assert botos.get_bot("telegram") is bot

    def test_botos_get_bot_missing(self):
        from praisonai.bots import BotOS
        botos = BotOS()
        assert botos.get_bot("telegram") is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Platform Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlatformRegistry:
    """Platform registry for extensible bot creation."""

    def test_registry_import(self):
        from praisonai.bots._registry import get_platform_registry
        reg = get_platform_registry()
        assert reg is not None

    def test_builtin_platforms_registered(self):
        from praisonai.bots._registry import get_platform_registry
        reg = get_platform_registry()
        assert "telegram" in reg
        assert "discord" in reg
        assert "slack" in reg
        assert "whatsapp" in reg

    def test_register_custom_platform(self):
        from praisonai.bots._registry import get_platform_registry, register_platform
        class CustomBot:
            pass
        register_platform("custom", CustomBot)
        reg = get_platform_registry()
        assert "custom" in reg
        # Clean up
        reg.pop("custom", None)

    def test_list_platforms(self):
        from praisonai.bots._registry import list_platforms
        platforms = list_platforms()
        assert isinstance(platforms, list)
        assert "telegram" in platforms


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. No performance impact
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestNoPerformanceImpact:
    """Importing BotOSProtocol/BotOSConfig should not pull heavy deps."""

    def test_protocol_import_lightweight(self):
        """Protocol import should not load telegram/discord/slack."""
        import sys
        # These should NOT be in sys.modules after importing protocol
        from praisonaiagents.bots.protocols import BotOSProtocol
        assert 'telegram' not in sys.modules
        assert 'discord' not in sys.modules
        assert 'slack_bolt' not in sys.modules

    def test_config_import_lightweight(self):
        from praisonaiagents.bots.config import BotOSConfig
        import sys
        assert 'telegram' not in sys.modules
        assert 'discord' not in sys.modules
