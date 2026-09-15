"""
Unit tests for bot CLI capabilities wiring.

Tests that BotCapabilities are correctly passed to Agent constructor.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestBotCapabilitiesWiring:
    """Test that bot capabilities are wired to Agent constructor."""
    
    def test_get_agent_kwargs_memory(self):
        """Test that --memory flag is converted to Agent kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(memory=True)
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("memory") is True
    
    def test_get_agent_kwargs_knowledge(self):
        """Test that --knowledge flag with sources is converted to Agent kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(
            knowledge=True,
            knowledge_sources=["docs.pdf", "data.txt"]
        )
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("knowledge") == ["docs.pdf", "data.txt"]
    
    def test_get_agent_kwargs_knowledge_no_sources(self):
        """Test that --knowledge flag without sources sets knowledge=True."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(knowledge=True)
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("knowledge") is True
    
    def test_get_agent_kwargs_skills(self):
        """Test that --skills flag is converted to Agent kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(skills=["web_search", "code_exec"])
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("skills") == ["web_search", "code_exec"]
    
    def test_get_agent_kwargs_thinking_medium(self):
        """Test that --thinking medium enables reflection."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="medium")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("reflection") is True
    
    def test_get_agent_kwargs_thinking_high(self):
        """Test that --thinking high enables reflection."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="high")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("reflection") is True
    
    def test_get_agent_kwargs_thinking_low(self):
        """Test that --thinking low does NOT enable reflection."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(thinking="low")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert "reflection" not in kwargs
    
    def test_get_agent_kwargs_model(self):
        """Test that --model is converted to Agent kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities(model="gpt-4o")
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs.get("llm") == "gpt-4o"
    
    def test_get_agent_kwargs_empty_capabilities(self):
        """Test that empty capabilities returns empty kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        handler = BotHandler()
        capabilities = BotCapabilities()
        
        kwargs = handler._get_agent_kwargs(capabilities)
        
        assert kwargs == {}
    
    def test_get_agent_kwargs_none_capabilities(self):
        """Test that None capabilities returns empty kwargs."""
        from praisonai_bot.cli.features.bots_cli import BotHandler
        
        handler = BotHandler()
        
        kwargs = handler._get_agent_kwargs(None)
        
        assert kwargs == {}
    
    @patch('praisonaiagents.Agent')
    def test_load_agent_passes_capabilities(self, mock_agent_class):
        """Test that _load_agent passes capabilities to Agent constructor."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        
        mock_agent = Mock()
        mock_agent_class.return_value = mock_agent
        
        handler = BotHandler()
        capabilities = BotCapabilities(
            memory=True,
            knowledge=True,
            knowledge_sources=["docs.pdf"],
            skills=["web_search"],
            thinking="medium",
            model="gpt-4o",
        )
        
        # Call _load_agent without a file (uses default agent)
        with patch.object(handler, '_build_tools', return_value=[]):
            _ = handler._load_agent(None, capabilities)
        
        # Verify Agent was called with the right kwargs
        call_kwargs = mock_agent_class.call_args[1]
        
        assert call_kwargs.get("memory") is True
        assert call_kwargs.get("knowledge") == ["docs.pdf"]
        assert call_kwargs.get("skills") == ["web_search"]
        assert call_kwargs.get("reflection") is True
        assert call_kwargs.get("llm") == "gpt-4o"


class TestBotCapabilitiesDataclass:
    """Test BotCapabilities dataclass."""
    
    def test_default_values(self):
        """Test default values are correct."""
        from praisonai_bot.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities()
        
        assert caps.memory is False
        assert caps.knowledge is False
        assert caps.knowledge_sources == []
        assert caps.skills == []
        assert caps.thinking is None
        assert caps.model is None
        assert caps.sandbox is False
    
    def test_to_dict(self):
        """Test to_dict method."""
        from praisonai_bot.cli.features.bots_cli import BotCapabilities
        
        caps = BotCapabilities(memory=True, model="gpt-4o")
        d = caps.to_dict()
        
        assert d["memory"] is True
        assert d["model"] == "gpt-4o"


class TestBuildCapabilitiesFromArgs:
    """Test _build_capabilities_from_args function."""
    
    def test_builds_from_args(self):
        """Test building capabilities from argparse namespace."""
        from praisonai_bot.cli.features.bots_cli import _build_capabilities_from_args
        from argparse import Namespace
        
        args = Namespace(
            memory=True,
            knowledge=True,
            knowledge_sources=["docs.pdf"],
            skills=["web_search"],
            thinking="medium",
            model="gpt-4o",
            browser=False,
            browser_profile="default",
            browser_headless=False,
            tools=[],
            skills_dir=None,
            memory_provider="default",
            web_search=False,
            web_provider="duckduckgo",
            sandbox=False,
            exec_enabled=False,
            auto_approve=False,
            session_id=None,
            user_id=None,
        )
        
        caps = _build_capabilities_from_args(args)
        
        assert caps.memory is True
        assert caps.knowledge is True
        assert caps.knowledge_sources == ["docs.pdf"]
        assert caps.skills == ["web_search"]
        assert caps.thinking == "medium"
        assert caps.model == "gpt-4o"


class TestBrowserToolWiring:
    """Test that --browser wires local praisonai-browser automation."""

    def _tool_names(self, tools):
        return [getattr(t, "__name__", type(t).__name__) for t in tools]

    def test_browser_uses_local_automation(self):
        """--browser attaches local browser_automate when praisonai-browser is available."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities

        handler = BotHandler()
        caps = BotCapabilities(model="gpt-4o-mini", browser=True, browser_headless=True)

        with patch("praisonai_bot._browser_bridge.browser_available", return_value=True):
            tools = handler._build_tools(caps)

        names = self._tool_names(tools)
        assert "browser_automate" in names
        assert "BrowserBaseTool" not in [type(t).__name__ for t in tools]

    def test_browser_falls_back_to_browserbase(self):
        """When praisonai-browser is unavailable, fall back to BrowserBaseTool."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities

        handler = BotHandler()
        caps = BotCapabilities(model="gpt-4o-mini", browser=True)

        fake_tool = Mock()
        fake_module = MagicMock()
        fake_module.BrowserBaseTool.return_value = fake_tool

        with patch("praisonai_bot._browser_bridge.browser_available", return_value=False), \
                patch.dict("sys.modules", {"praisonai_tools": fake_module}):
            tools = handler._build_tools(caps)

        assert fake_tool in tools
        assert "browser_automate" not in self._tool_names(tools)

    def test_browser_available_requires_playwright(self):
        """browser_available() is False when the Playwright runtime is missing."""
        import builtins

        from praisonai_bot import _browser_bridge

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "playwright" or name.startswith("playwright."):
                raise ImportError("no playwright")
            return real_import(name, *args, **kwargs)

        with patch.object(_browser_bridge, "_ensure_praisonai_browser", return_value=None), \
                patch.dict("sys.modules", {"praisonai_browser": MagicMock()}), \
                patch.object(builtins, "__import__", side_effect=_fake_import):
            assert _browser_bridge.browser_available() is False


class TestUnknownUserPolicyWiring:
    """Issue #5093: bot.yaml unknown_user_policy must reach BotConfig via CLI."""

    def test_policy_kwargs_forwards_policy_and_owner(self):
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities

        caps = BotCapabilities(
            unknown_user_policy="ALLOW", owner_user_id="  987654321  "
        )
        kwargs = BotHandler._policy_kwargs(caps)
        assert kwargs["unknown_user_policy"] == "allow"
        assert kwargs["owner_user_id"] == "987654321"

    def test_policy_kwargs_omits_unset(self):
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities

        assert BotHandler._policy_kwargs(BotCapabilities()) == {}
        assert BotHandler._policy_kwargs(None) == {}

    def test_capabilities_to_botconfig_defaults_deny_when_omitted(self):
        """Omitting the field keeps BotConfig's secure ``deny`` default."""
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        from praisonaiagents.bots import BotConfig

        cfg = BotConfig(token="x", **BotHandler._policy_kwargs(BotCapabilities()))
        assert cfg.unknown_user_policy == "deny"

    def test_capabilities_to_botconfig_applies_allow(self):
        from praisonai_bot.cli.features.bots_cli import BotHandler, BotCapabilities
        from praisonaiagents.bots import BotConfig

        caps = BotCapabilities(unknown_user_policy="allow")
        cfg = BotConfig(token="x", **BotHandler._policy_kwargs(caps))
        assert cfg.unknown_user_policy == "allow"


class TestUnknownUserPolicyYamlSchema:
    """Issue #5093: unknown_user_policy must survive YAML validation."""

    def test_top_level_single_bot_policy_reaches_channel(self):
        """A top-level ``unknown_user_policy`` migrates onto the channel."""
        from praisonai_bot.bots._config_schema import validate_gateway_config

        cfg = validate_gateway_config(
            {
                "platform": "telegram",
                "token": "fake",
                "unknown_user_policy": "allow",
                "agent": {"name": "Test", "llm": "gpt-4o-mini"},
            },
            apply_env_substitution=False,
        )
        channel = cfg.channels["telegram"]
        assert channel.unknown_user_policy == "allow"

    def test_channel_level_policy_preserved(self):
        from praisonai_bot.bots._config_schema import validate_gateway_config

        cfg = validate_gateway_config(
            {
                "channels": {
                    "telegram": {"token": "fake", "unknown_user_policy": "pair"}
                },
                "agent": {"name": "Test", "llm": "gpt-4o-mini"},
            },
            apply_env_substitution=False,
        )
        assert cfg.channels["telegram"].unknown_user_policy == "pair"

    def test_invalid_policy_rejected(self):
        from praisonai_bot.bots._config_schema import validate_gateway_config

        with pytest.raises(ValueError):
            validate_gateway_config(
                {
                    "channels": {
                        "telegram": {"token": "fake", "unknown_user_policy": "alow"}
                    },
                    "agent": {"name": "Test", "llm": "gpt-4o-mini"},
                },
                apply_env_substitution=False,
            )

    def test_invalid_top_level_policy_rejected_with_channels(self):
        """A top-level typo must fail closed even when ``channels:`` exists.

        Without the top-level validator this bypasses the channel rule (the
        migration only runs when ``platform`` is set and no channels exist).
        """
        from praisonai_bot.bots._config_schema import validate_gateway_config

        with pytest.raises(ValueError):
            validate_gateway_config(
                {
                    "unknown_user_policy": "alow",
                    "channels": {"telegram": {"token": "fake"}},
                    "agent": {"name": "Test", "llm": "gpt-4o-mini"},
                },
                apply_env_substitution=False,
            )

    def test_numeric_owner_id_channel_coerced_to_string(self):
        """An unquoted numeric channel owner id must not fail validation."""
        from praisonai_bot.bots._config_schema import validate_gateway_config

        cfg = validate_gateway_config(
            {
                "channels": {
                    "telegram": {"token": "fake", "owner_user_id": 987654321}
                },
                "agent": {"name": "Test", "llm": "gpt-4o-mini"},
            },
            apply_env_substitution=False,
        )
        assert cfg.channels["telegram"].owner_user_id == "987654321"

    def test_numeric_owner_id_top_level_migrates_as_string(self):
        """A top-level numeric owner id migrates onto the channel as a string."""
        from praisonai_bot.bots._config_schema import validate_gateway_config

        cfg = validate_gateway_config(
            {
                "platform": "telegram",
                "token": "fake",
                "owner_user_id": 987654321,
                "unknown_user_policy": "pair",
                "agent": {"name": "Test", "llm": "gpt-4o-mini"},
            },
            apply_env_substitution=False,
        )
        channel = cfg.channels["telegram"]
        assert channel.owner_user_id == "987654321"
        assert channel.unknown_user_policy == "pair"


class TestUnknownUserPolicyStartupInfo:
    """Issue #5093: startup banner must not falsely confirm the policy."""

    def _capture(self, platform, capabilities, policy_applied):
        from praisonai_bot.cli.features.bots_cli import BotHandler

        lines = []
        with patch("builtins.print", side_effect=lambda *a, **k: lines.append(" ".join(str(x) for x in a))):
            BotHandler()._print_startup_info(
                platform, capabilities, policy_applied=policy_applied
            )
        return "\n".join(lines)

    def test_policy_printed_when_applied(self):
        from praisonai_bot.cli.features.bots_cli import BotCapabilities

        out = self._capture(
            "Telegram", BotCapabilities(unknown_user_policy="allow"), True
        )
        assert "unknown_user_policy: allow" in out

    def test_effective_deny_printed_when_omitted_but_applied(self):
        from praisonai_bot.cli.features.bots_cli import BotCapabilities

        out = self._capture("Telegram", BotCapabilities(), True)
        assert "unknown_user_policy: deny" in out

    def test_policy_not_printed_on_unsupported_platform(self):
        from praisonai_bot.cli.features.bots_cli import BotCapabilities

        out = self._capture(
            "WhatsApp", BotCapabilities(unknown_user_policy="allow"), False
        )
        assert "unknown_user_policy" not in out
