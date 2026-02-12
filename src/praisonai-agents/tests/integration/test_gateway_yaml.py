"""
Integration tests for Gateway YAML configuration loading.

Tests the full flow: YAML dict → MultiChannelGatewayConfig → channel routing.
Uses mocked environment variables — no actual bot tokens or servers needed.
"""

import os
from unittest.mock import patch


class TestGatewayYamlParsing:
    """Tests for parsing gateway.yaml-style configuration."""

    SAMPLE_CONFIG = {
        "gateway": {
            "host": "127.0.0.1",
            "port": 8765,
        },
        "agents": {
            "personal": {
                "instructions": "You are a helpful personal assistant",
                "model": "gpt-4o-mini",
                "memory": True,
            },
            "support": {
                "instructions": "You are a customer support agent",
                "model": "gpt-4o",
            },
        },
        "channels": {
            "telegram": {
                "token": "${TELEGRAM_BOT_TOKEN}",
                "routes": {
                    "dm": "personal",
                    "group": "support",
                    "default": "personal",
                },
            },
            "discord": {
                "token": "${DISCORD_BOT_TOKEN}",
                "routes": {
                    "default": "personal",
                },
            },
            "slack": {
                "token": "${SLACK_BOT_TOKEN}",
                "app_token": "${SLACK_APP_TOKEN}",
                "routes": {
                    "dm": "support",
                    "default": "support",
                },
            },
        },
    }

    def test_parse_gateway_section(self):
        """Test parsing the gateway section."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        assert config.gateway.host == "127.0.0.1"
        assert config.gateway.port == 8765

    def test_parse_agents_section(self):
        """Test parsing the agents section."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        assert len(config.agents) == 2
        assert "personal" in config.agents
        assert "support" in config.agents
        assert config.agents["personal"]["model"] == "gpt-4o-mini"
        assert config.agents["support"]["model"] == "gpt-4o"
        assert config.agents["personal"]["memory"] is True

    def test_parse_channels_section(self):
        """Test parsing the channels section."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        assert len(config.channels) == 3
        assert "telegram" in config.channels
        assert "discord" in config.channels
        assert "slack" in config.channels

    def test_channel_routing_telegram(self):
        """Test Telegram routing: dm→personal, group→support."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        tg = config.channels["telegram"]
        assert tg.get_agent_id("dm") == "personal"
        assert tg.get_agent_id("group") == "support"
        assert tg.get_agent_id("default") == "personal"

    def test_channel_routing_discord(self):
        """Test Discord routing: default→personal."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        dc = config.channels["discord"]
        assert dc.get_agent_id("default") == "personal"
        assert dc.get_agent_id("dm") == "personal"

    def test_channel_routing_slack(self):
        """Test Slack routing: dm→support, default→support."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        sl = config.channels["slack"]
        assert sl.get_agent_id("dm") == "support"
        assert sl.get_agent_id("default") == "support"

    def test_parse_empty_config(self):
        """Test parsing empty configuration."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict({})
        assert config.agents == {}
        assert config.channels == {}

    def test_parse_agents_only(self):
        """Test parsing config with only agents section."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        data = {
            "agents": {
                "helper": {"instructions": "Help people"},
            },
        }
        config = MultiChannelGatewayConfig.from_dict(data)
        assert "helper" in config.agents
        assert config.channels == {}

    def test_roundtrip_to_dict(self):
        """Test config serialization roundtrip."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig

        config = MultiChannelGatewayConfig.from_dict(self.SAMPLE_CONFIG)
        d = config.to_dict()
        assert "gateway" in d
        assert "agents" in d
        assert "channels" in d


class TestEnvVarSubstitution:
    """Tests for environment variable substitution in gateway config."""

    @patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "tg-secret-123",
        "DISCORD_BOT_TOKEN": "dc-secret-456",
    })
    def test_env_var_in_token(self):
        """Test that ${VAR} tokens are resolved from environment."""
        token_value = "${TELEGRAM_BOT_TOKEN}"
        resolved = os.environ.get("TELEGRAM_BOT_TOKEN", token_value)
        assert resolved == "tg-secret-123"

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_var(self):
        """Test behavior when env var is not set."""
        token_value = "${MISSING_TOKEN}"
        var_name = token_value.strip("${}")
        resolved = os.environ.get(var_name, "")
        assert resolved == ""

    @patch.dict(os.environ, {"MY_TOKEN": "my-value"})
    def test_env_var_pattern_matching(self):
        """Test ${VAR} pattern extraction."""
        import re

        raw = "${MY_TOKEN}"
        pattern = r"\$\{(\w+)\}"
        match = re.match(pattern, raw)
        assert match is not None
        var_name = match.group(1)
        assert var_name == "MY_TOKEN"
        assert os.environ.get(var_name) == "my-value"


class TestMultiAgentRouting:
    """Integration tests for multi-agent routing scenarios."""

    def test_dm_routes_to_personal_agent(self):
        """Test that DM context routes to personal agent."""
        from praisonaiagents.gateway import ChannelRouteConfig

        route = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal", "group": "support", "default": "personal"},
        )
        assert route.get_agent_id("dm") == "personal"

    def test_group_routes_to_support_agent(self):
        """Test that group context routes to support agent."""
        from praisonaiagents.gateway import ChannelRouteConfig

        route = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal", "group": "support", "default": "personal"},
        )
        assert route.get_agent_id("group") == "support"

    def test_unknown_context_falls_to_default(self):
        """Test that unknown context falls back to default."""
        from praisonaiagents.gateway import ChannelRouteConfig

        route = ChannelRouteConfig(
            channel_type="discord",
            routes={"default": "main"},
        )
        assert route.get_agent_id("thread") == "main"
        assert route.get_agent_id("forum") == "main"

    def test_multiple_channels_independent_routing(self):
        """Test that each channel routes independently."""
        from praisonaiagents.gateway import ChannelRouteConfig

        telegram = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal", "default": "personal"},
        )
        discord = ChannelRouteConfig(
            channel_type="discord",
            routes={"dm": "support", "default": "support"},
        )
        assert telegram.get_agent_id("dm") == "personal"
        assert discord.get_agent_id("dm") == "support"

    def test_all_standard_contexts(self):
        """Test routing with all standard context types."""
        from praisonaiagents.gateway import ChannelRouteConfig

        route = ChannelRouteConfig(
            channel_type="slack",
            routes={
                "dm": "agent_a",
                "group": "agent_b",
                "channel": "agent_c",
                "default": "agent_d",
            },
        )
        assert route.get_agent_id("dm") == "agent_a"
        assert route.get_agent_id("group") == "agent_b"
        assert route.get_agent_id("channel") == "agent_c"
        assert route.get_agent_id("default") == "agent_d"
        assert route.get_agent_id("unknown") == "agent_d"
