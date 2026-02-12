"""
Tests for Gateway Configuration additions.

TDD: Tests for ChannelRouteConfig, MultiChannelGatewayConfig,
and existing GatewayConfig/SessionConfig.
"""

from praisonaiagents.gateway import GatewayConfig, SessionConfig


class TestSessionConfig:
    """Tests for existing SessionConfig dataclass."""

    def test_session_config_defaults(self):
        """Test SessionConfig has correct defaults."""
        config = SessionConfig()
        assert config.timeout == 3600
        assert config.max_messages == 1000
        assert config.persist is False
        assert config.persist_path is None
        assert config.metadata == {}

    def test_session_config_custom(self):
        """Test SessionConfig with custom values."""
        config = SessionConfig(
            timeout=7200,
            max_messages=500,
            persist=True,
            persist_path="/tmp/sessions",
            metadata={"env": "test"},
        )
        assert config.timeout == 7200
        assert config.max_messages == 500
        assert config.persist is True
        assert config.persist_path == "/tmp/sessions"
        assert config.metadata == {"env": "test"}

    def test_session_config_to_dict(self):
        """Test SessionConfig serialization."""
        config = SessionConfig(timeout=1800, persist=True)
        d = config.to_dict()
        assert d["timeout"] == 1800
        assert d["persist"] is True
        assert "max_messages" in d
        assert "metadata" in d


class TestGatewayConfig:
    """Tests for existing GatewayConfig dataclass."""

    def test_gateway_config_defaults(self):
        """Test GatewayConfig has correct defaults."""
        config = GatewayConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.cors_origins == ["*"]
        assert config.auth_token is None
        assert config.max_connections == 1000
        assert config.max_sessions_per_agent == 0
        assert config.heartbeat_interval == 30
        assert config.reconnect_timeout == 60

    def test_gateway_config_custom(self):
        """Test GatewayConfig with custom values."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=9000,
            auth_token="secret",
            max_connections=500,
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.auth_token == "secret"
        assert config.max_connections == 500

    def test_gateway_config_to_dict_hides_token(self):
        """Test that to_dict masks the auth token."""
        config = GatewayConfig(auth_token="my-secret-token")
        d = config.to_dict()
        assert d["auth_token"] == "***"

    def test_gateway_config_to_dict_no_token(self):
        """Test that to_dict shows None when no token."""
        config = GatewayConfig()
        d = config.to_dict()
        assert d["auth_token"] is None

    def test_gateway_config_ws_url(self):
        """Test WebSocket URL generation."""
        config = GatewayConfig(host="localhost", port=8080)
        assert config.ws_url == "ws://localhost:8080"

    def test_gateway_config_http_url(self):
        """Test HTTP URL generation."""
        config = GatewayConfig(host="localhost", port=8080)
        assert config.http_url == "http://localhost:8080"

    def test_gateway_config_is_secure_false(self):
        """Test is_secure when no SSL configured."""
        config = GatewayConfig()
        assert config.is_secure is False

    def test_gateway_config_is_secure_true(self):
        """Test is_secure when SSL is configured."""
        config = GatewayConfig(ssl_cert="/path/cert.pem", ssl_key="/path/key.pem")
        assert config.is_secure is True

    def test_gateway_config_secure_urls(self):
        """Test secure URL generation."""
        config = GatewayConfig(
            host="localhost",
            port=443,
            ssl_cert="/path/cert.pem",
            ssl_key="/path/key.pem",
        )
        assert config.ws_url == "wss://localhost:443"
        assert config.http_url == "https://localhost:443"

    def test_gateway_config_session_config(self):
        """Test nested SessionConfig."""
        session_config = SessionConfig(timeout=600)
        config = GatewayConfig(session_config=session_config)
        assert config.session_config.timeout == 600


class TestChannelRouteConfig:
    """Tests for ChannelRouteConfig dataclass (added by Agent 3)."""

    def test_import(self):
        """Test ChannelRouteConfig can be imported."""
        from praisonaiagents.gateway import ChannelRouteConfig
        assert ChannelRouteConfig is not None

    def test_creation_defaults(self):
        """Test ChannelRouteConfig with defaults."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(channel_type="telegram")
        assert config.channel_type == "telegram"
        assert config.token_env == ""
        assert config.app_token_env is None
        assert config.routes == {"default": "default"}
        assert config.enabled is True
        assert config.metadata == {}

    def test_creation_custom(self):
        """Test ChannelRouteConfig with custom values."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="discord",
            token_env="DISCORD_BOT_TOKEN",
            routes={"dm": "personal", "group": "support", "default": "personal"},
            enabled=True,
            metadata={"guild_id": "123"},
        )
        assert config.channel_type == "discord"
        assert config.token_env == "DISCORD_BOT_TOKEN"
        assert config.routes["dm"] == "personal"
        assert config.routes["group"] == "support"

    def test_get_agent_id_direct(self):
        """Test get_agent_id with direct match."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal", "group": "support", "default": "fallback"},
        )
        assert config.get_agent_id("dm") == "personal"
        assert config.get_agent_id("group") == "support"

    def test_get_agent_id_fallback(self):
        """Test get_agent_id falls back to default."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal", "default": "fallback"},
        )
        assert config.get_agent_id("group") == "fallback"
        assert config.get_agent_id("channel") == "fallback"

    def test_get_agent_id_no_default(self):
        """Test get_agent_id with no default route."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="telegram",
            routes={"dm": "personal"},
        )
        result = config.get_agent_id("group")
        assert result == "default"

    def test_get_agent_id_default_context(self):
        """Test get_agent_id with default context arg."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="telegram",
            routes={"default": "main_agent"},
        )
        assert config.get_agent_id() == "main_agent"

    def test_to_dict(self):
        """Test ChannelRouteConfig serialization."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="slack",
            token_env="SLACK_TOKEN",
            routes={"default": "support"},
        )
        d = config.to_dict()
        assert d["channel_type"] == "slack"
        assert d["token_env"] == "SLACK_TOKEN"
        assert d["routes"] == {"default": "support"}
        assert d["enabled"] is True

    def test_disabled_channel(self):
        """Test disabled channel config."""
        from praisonaiagents.gateway import ChannelRouteConfig
        config = ChannelRouteConfig(
            channel_type="telegram",
            enabled=False,
        )
        assert config.enabled is False


class TestMultiChannelGatewayConfig:
    """Tests for MultiChannelGatewayConfig dataclass (added by Agent 3)."""

    def test_import(self):
        """Test MultiChannelGatewayConfig can be imported."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig
        assert MultiChannelGatewayConfig is not None

    def test_creation_defaults(self):
        """Test MultiChannelGatewayConfig with defaults."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig
        config = MultiChannelGatewayConfig()
        assert isinstance(config.gateway, GatewayConfig)
        assert config.agents == {}
        assert config.channels == {}

    def test_creation_with_agents(self):
        """Test MultiChannelGatewayConfig with agents."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig
        config = MultiChannelGatewayConfig(
            agents={
                "personal": {"instructions": "Be helpful", "model": "gpt-4o-mini"},
                "support": {"instructions": "Customer support", "model": "gpt-4o"},
            }
        )
        assert "personal" in config.agents
        assert config.agents["personal"]["model"] == "gpt-4o-mini"
        assert "support" in config.agents

    def test_creation_with_channels(self):
        """Test MultiChannelGatewayConfig with channels."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig, ChannelRouteConfig
        tg = ChannelRouteConfig(
            channel_type="telegram",
            token_env="TG_TOKEN",
            routes={"dm": "personal", "default": "personal"},
        )
        config = MultiChannelGatewayConfig(channels={"telegram": tg})
        assert "telegram" in config.channels
        assert config.channels["telegram"].channel_type == "telegram"

    def test_from_dict_full(self):
        """Test from_dict with full YAML-like dictionary."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig
        data = {
            "gateway": {"host": "0.0.0.0", "port": 9000},
            "agents": {
                "personal": {"instructions": "Be helpful", "model": "gpt-4o-mini", "memory": True},
                "support": {"instructions": "Customer support", "model": "gpt-4o"},
            },
            "channels": {
                "telegram": {
                    "token": "${TELEGRAM_BOT_TOKEN}",
                    "routes": {"dm": "personal", "group": "support", "default": "personal"},
                },
                "discord": {
                    "token": "${DISCORD_BOT_TOKEN}",
                    "routes": {"default": "personal"},
                },
            },
        }
        config = MultiChannelGatewayConfig.from_dict(data)
        assert config.gateway.port == 9000
        assert "personal" in config.agents
        assert "support" in config.agents
        assert "telegram" in config.channels
        assert "discord" in config.channels

    def test_to_dict(self):
        """Test MultiChannelGatewayConfig serialization."""
        from praisonaiagents.gateway import MultiChannelGatewayConfig
        config = MultiChannelGatewayConfig(
            agents={"test": {"instructions": "Test agent"}},
        )
        d = config.to_dict()
        assert "gateway" in d
        assert "agents" in d
        assert "channels" in d

    def test_stdlib_only(self):
        """Verify these classes use only stdlib - no external deps."""
        import sys
        from praisonaiagents.gateway.config import ChannelRouteConfig, MultiChannelGatewayConfig
        module = sys.modules["praisonaiagents.gateway.config"]
        source_file = module.__file__
        with open(source_file, "r") as f:
            content = f.read()
        for dep in ["chromadb", "fastapi", "uvicorn", "pydantic", "litellm"]:
            assert f"import {dep}" not in content, f"Found heavy dep '{dep}' in config.py"


class TestChatCommandInfo:
    """Tests for ChatCommandInfo dataclass (added by Agent 3)."""

    def test_import(self):
        """Test ChatCommandInfo can be imported."""
        from praisonaiagents.bots import ChatCommandInfo
        assert ChatCommandInfo is not None

    def test_creation_minimal(self):
        """Test ChatCommandInfo with minimal fields."""
        from praisonaiagents.bots import ChatCommandInfo
        cmd = ChatCommandInfo(name="status")
        assert cmd.name == "status"
        assert cmd.description == ""
        assert cmd.hidden is False

    def test_creation_full(self):
        """Test ChatCommandInfo with all fields."""
        from praisonaiagents.bots import ChatCommandInfo
        cmd = ChatCommandInfo(
            name="help",
            description="Show available commands",
            usage="/help",
            hidden=False,
        )
        assert cmd.name == "help"
        assert cmd.description == "Show available commands"
        assert cmd.usage == "/help"
        assert cmd.hidden is False

    def test_hidden_command(self):
        """Test hidden ChatCommandInfo."""
        from praisonaiagents.bots import ChatCommandInfo
        cmd = ChatCommandInfo(name="debug", hidden=True)
        assert cmd.hidden is True

    def test_stdlib_only(self):
        """Verify bots/protocols.py uses only stdlib."""
        import sys
        from praisonaiagents.bots.protocols import BotProtocol
        module = sys.modules["praisonaiagents.bots.protocols"]
        source_file = module.__file__
        with open(source_file, "r") as f:
            content = f.read()
        for dep in ["chromadb", "fastapi", "uvicorn", "litellm"]:
            assert f"import {dep}" not in content, f"Found heavy dep '{dep}' in protocols.py"
