"""Unit tests for the managed agent backend integration.

Tests:
- ManagedBackendProtocol conformance
- ManagedBackendConfig dataclass
- Agent -> execution_mixin._delegate_to_backend -> ManagedAgentIntegration.execute
- Usage tracking, custom tool callbacks, tool confirmation
Uses mocks to avoid real API calls.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ── Test ManagedBackendProtocol & ManagedBackendConfig (Core SDK) ──

class TestManagedBackendProtocol:
    """Verify the protocol and config dataclass in the Core SDK."""

    def test_protocol_importable(self):
        from praisonaiagents.agent.protocols import ManagedBackendProtocol
        assert ManagedBackendProtocol is not None

    def test_config_importable(self):
        from praisonaiagents.agent.protocols import ManagedBackendConfig
        assert ManagedBackendConfig is not None

    def test_config_defaults(self):
        from praisonaiagents.agent.protocols import ManagedBackendConfig
        cfg = ManagedBackendConfig()
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.name == "PraisonAI Managed Agent"
        assert cfg.tools == [{"type": "agent_toolset_20260401"}]
        assert cfg.networking == {"type": "unrestricted"}
        assert cfg.packages is None
        assert cfg.mcp_servers == []
        assert cfg.skills == []
        assert cfg.resources == []
        assert cfg.vault_ids == []

    def test_config_custom_values(self):
        from praisonaiagents.agent.protocols import ManagedBackendConfig
        cfg = ManagedBackendConfig(
            model="claude-opus-4",
            name="Custom Agent",
            packages={"pip": ["pandas"]},
            networking={"type": "limited", "allowed_hosts": ["example.com"]},
        )
        assert cfg.model == "claude-opus-4"
        assert cfg.packages == {"pip": ["pandas"]}

    def test_config_converts_to_dict(self):
        from dataclasses import asdict
        from praisonaiagents.agent.protocols import ManagedBackendConfig
        cfg = ManagedBackendConfig(model="test-model")
        d = asdict(cfg)
        assert isinstance(d, dict)
        assert d["model"] == "test-model"

    def test_mock_backend_satisfies_protocol(self):
        """A minimal mock with execute/stream/reset should pass isinstance check."""
        from praisonaiagents.agent.protocols import ManagedBackendProtocol

        class _MockBackend:
            async def execute(self, prompt: str, **kwargs) -> str:
                return "mock"
            async def stream(self, prompt: str, **kwargs):
                yield "mock"
            def reset_session(self) -> None:
                pass
            def reset_all(self) -> None:
                pass

        assert isinstance(_MockBackend(), ManagedBackendProtocol)

    def test_lazy_import_from_top_level(self):
        """ManagedBackendProtocol should be accessible via praisonaiagents.__getattr__."""
        from praisonaiagents import ManagedBackendProtocol, ManagedBackendConfig
        assert ManagedBackendProtocol is not None
        assert ManagedBackendConfig is not None


# ── Test Agent backend delegation (execution_mixin.py) ──

class TestBackendDelegation:
    """Test that Agent correctly delegates to backend when set."""

    def test_agent_accepts_backend_param(self):
        """Agent.__init__ should accept backend= kwarg."""
        from praisonaiagents import Agent

        mock_backend = MagicMock()
        mock_backend.execute = AsyncMock(return_value="mock response")

        agent = Agent(name="test", instructions="test", backend=mock_backend)
        assert agent.backend is mock_backend

    def test_agent_backend_default_none(self):
        """Agent should default to backend=None."""
        from praisonaiagents import Agent

        agent = Agent(name="test", instructions="test")
        assert agent.backend is None

    def test_run_delegates_to_backend(self):
        """Agent.run() should delegate to backend.execute() when backend is set."""
        from praisonaiagents import Agent

        mock_backend = MagicMock()
        mock_backend.execute = AsyncMock(return_value="backend result")

        agent = Agent(name="test", instructions="test", backend=mock_backend)
        result = agent.run("hello")

        assert result == "backend result"
        mock_backend.execute.assert_called_once()

    def test_start_delegates_to_backend(self):
        """Agent.start() should delegate to backend.execute() when backend is set."""
        from praisonaiagents import Agent

        mock_backend = MagicMock()
        mock_backend.execute = AsyncMock(return_value="start result")

        agent = Agent(name="test", instructions="test", backend=mock_backend)
        result = agent.start("hello")

        assert result == "start result"
        mock_backend.execute.assert_called_once()

    def test_backend_missing_execute_raises(self):
        """Backend without execute() should raise RuntimeError."""
        from praisonaiagents import Agent

        mock_backend = MagicMock(spec=[])  # No methods

        agent = Agent(name="test", instructions="test", backend=mock_backend)
        with pytest.raises(RuntimeError, match="does not support execute"):
            agent.run("hello")

    def test_no_backend_uses_normal_path(self):
        """Agent without backend should use normal LLM path."""
        from praisonaiagents import Agent

        agent = Agent(
            name="test",
            instructions="test",
            llm="gpt-4o-mini",
        )
        # Should not raise; just ensure backend is None
        assert agent.backend is None


# ── Test ManagedAgentIntegration class ──

class TestManagedAgentIntegration:
    """Test the ManagedAgentIntegration wrapper."""

    def test_init_default_provider(self):
        """Default provider should be anthropic."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            m = ManagedAgentIntegration()
            assert m.provider == "anthropic"
            assert m.api_key == "test-key"

    def test_init_custom_config_dict(self):
        """Dict config should be stored correctly."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(
            api_key="test-key",
            config={"model": "claude-sonnet-4-6"},
            instructions="Be concise.",
        )
        assert m._cfg["model"] == "claude-sonnet-4-6"
        assert m.instructions == "Be concise."

    def test_init_config_dataclass(self):
        """ManagedBackendConfig dataclass should be auto-converted to dict."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        from praisonaiagents.agent.protocols import ManagedBackendConfig

        cfg = ManagedBackendConfig(
            model="claude-opus-4",
            name="DC Agent",
            packages={"pip": ["numpy"]},
        )
        m = ManagedAgentIntegration(api_key="test-key", config=cfg)
        assert m._cfg["model"] == "claude-opus-4"
        assert m._cfg["name"] == "DC Agent"
        assert m._cfg["packages"] == {"pip": ["numpy"]}

    def test_init_no_api_key_no_env(self):
        """Should not crash without API key — will fail at execute time."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        with patch.dict("os.environ", {}, clear=True):
            m = ManagedAgentIntegration(api_key=None)
            assert m.api_key is None

    def test_get_client_raises_without_key(self):
        """_get_client should raise if no API key."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key=None)
        m.api_key = None  # Force no key
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not set"):
            m._get_client()

    def test_get_client_raises_without_sdk(self):
        """_get_client should raise if anthropic SDK not installed."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="anthropic SDK required"):
                m._client = None  # Force re-init
                m._get_client()

    def test_reset_session(self):
        """reset_session should clear cached session."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")
        m._session_id = "sess-123"
        m.reset_session()
        assert m._session_id is None

    def test_reset_all(self):
        """reset_all should clear everything including usage counters."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")
        m.agent_id = "agent-123"
        m.agent_version = 3
        m.environment_id = "env-123"
        m._session_id = "sess-123"
        m.total_input_tokens = 100
        m.total_output_tokens = 200
        m.reset_all()
        assert m.agent_id is None
        assert m.agent_version is None
        assert m.environment_id is None
        assert m._session_id is None
        assert m._client is None
        assert m.total_input_tokens == 0
        assert m.total_output_tokens == 0

    def _make_mock_client(self, events):
        """Helper: create a mock Anthropic client with given event sequence."""
        mock_client = MagicMock()
        mock_agent = MagicMock(id="agent-001", version=1)
        mock_client.beta.agents.create.return_value = mock_agent
        mock_env = MagicMock(id="env-001")
        mock_client.beta.environments.create.return_value = mock_env
        mock_session = MagicMock(id="sess-001")
        mock_client.beta.sessions.create.return_value = mock_session
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=iter(events))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_client.beta.sessions.events.stream.return_value = mock_stream_ctx
        mock_client.beta.sessions.events.send = MagicMock()
        return mock_client

    def test_execute_sync_with_mock_sdk(self):
        """_execute_sync should orchestrate create+stream correctly."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")

        mock_event_msg = MagicMock(type="agent.message", usage=None)
        mock_block = MagicMock(text="Hello from managed agent!")
        mock_event_msg.content = [mock_block]
        mock_event_idle = MagicMock(type="session.status_idle", usage=None)

        mock_client = self._make_mock_client([mock_event_msg, mock_event_idle])
        m._client = mock_client

        result = m._execute_sync("test prompt")
        assert result == "Hello from managed agent!"
        mock_client.beta.agents.create.assert_called_once()
        mock_client.beta.environments.create.assert_called_once()
        mock_client.beta.sessions.create.assert_called_once()

    def test_cached_ids_reused(self):
        """Second call should reuse cached agent/env/session IDs."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")
        m.agent_id = "agent-cached"
        m.environment_id = "env-cached"
        m._session_id = "sess-cached"

        mock_event = MagicMock(type="agent.message", usage=None)
        mock_block = MagicMock(text="cached response")
        mock_event.content = [mock_block]
        mock_idle = MagicMock(type="session.status_idle", usage=None)

        mock_client = self._make_mock_client([mock_event, mock_idle])
        m._client = mock_client

        result = m._execute_sync("test")
        assert result == "cached response"
        mock_client.beta.agents.create.assert_not_called()
        mock_client.beta.environments.create.assert_not_called()
        mock_client.beta.sessions.create.assert_not_called()

    def test_usage_tracking(self):
        """Token usage should accumulate across events."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")

        usage1 = MagicMock(input_tokens=10, output_tokens=20)
        usage2 = MagicMock(input_tokens=5, output_tokens=15)

        ev1 = MagicMock(type="agent.message", usage=usage1)
        ev1.content = [MagicMock(text="hi")]
        ev2 = MagicMock(type="agent.message", usage=usage2)
        ev2.content = [MagicMock(text=" there")]
        ev_idle = MagicMock(type="session.status_idle", usage=None)

        mock_client = self._make_mock_client([ev1, ev2, ev_idle])
        m._client = mock_client

        m._execute_sync("count tokens")
        assert m.total_input_tokens == 15
        assert m.total_output_tokens == 35

    def test_custom_tool_callback(self):
        """on_custom_tool should be called for agent.custom_tool_use events."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        calls = []
        def my_tool(name, inp):
            calls.append((name, inp))
            return "tool result"

        m = ManagedAgentIntegration(api_key="test-key", on_custom_tool=my_tool)

        ev_custom = MagicMock(type="agent.custom_tool_use", usage=None)
        ev_custom.name = "lookup_db"
        ev_custom.input = {"query": "select 1"}
        ev_custom.id = "tu-001"
        ev_idle = MagicMock(type="session.status_idle", usage=None)

        mock_client = self._make_mock_client([ev_custom, ev_idle])
        m._client = mock_client

        m._execute_sync("use custom tool")
        assert len(calls) == 1
        assert calls[0] == ("lookup_db", {"query": "select 1"})
        # Verify result was sent back
        send_calls = mock_client.beta.sessions.events.send.call_args_list
        # First call is user.message, second is custom_tool_result
        assert len(send_calls) >= 2

    def test_tool_confirmation_callback(self):
        """on_tool_confirmation should be called for needs_confirmation events."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        confirmations = []
        def confirm(info):
            confirmations.append(info)
            return True

        m = ManagedAgentIntegration(api_key="test-key", on_tool_confirmation=confirm)

        ev_tool = MagicMock(type="agent.tool_use", usage=None)
        ev_tool.name = "bash"
        ev_tool.needs_confirmation = True
        ev_tool.input = {"command": "ls"}
        ev_tool.id = "tu-002"
        ev_idle = MagicMock(type="session.status_idle", usage=None)

        mock_client = self._make_mock_client([ev_tool, ev_idle])
        m._client = mock_client

        m._execute_sync("confirm tool")
        assert len(confirmations) == 1
        assert confirmations[0]["name"] == "bash"

    def test_ensure_agent_passes_optional_fields(self):
        """Optional agent fields (mcp_servers, skills, etc.) should be forwarded."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(
            api_key="test-key",
            config={
                "model": "claude-sonnet-4-6",
                "mcp_servers": [{"type": "url", "url": "https://mcp.example.com/sse"}],
                "skills": [{"type": "anthropic", "name": "computer_use"}],
                "callable_agents": [{"agent_id": "agent-other"}],
                "metadata": {"team": "eng"},
            },
        )
        mock_client = MagicMock()
        mock_agent = MagicMock(id="agent-x", version=1)
        mock_client.beta.agents.create.return_value = mock_agent
        m._client = mock_client

        m._ensure_agent()
        call_kwargs = mock_client.beta.agents.create.call_args
        assert "mcp_servers" in call_kwargs.kwargs
        assert "skills" in call_kwargs.kwargs
        assert "callable_agents" in call_kwargs.kwargs
        assert "metadata" in call_kwargs.kwargs

    def test_ensure_session_passes_resources_and_vaults(self):
        """resources and vault_ids should be forwarded to session creation."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(
            api_key="test-key",
            config={
                "resources": [{"type": "file", "file_id": "file-123"}],
                "vault_ids": ["vault-abc"],
            },
        )
        m.agent_id = "agent-pre"
        m.environment_id = "env-pre"
        mock_client = MagicMock()
        mock_session = MagicMock(id="sess-new")
        mock_client.beta.sessions.create.return_value = mock_session
        m._client = mock_client

        m._ensure_session()
        call_kwargs = mock_client.beta.sessions.create.call_args
        assert "resources" in call_kwargs.kwargs
        assert "vault_ids" in call_kwargs.kwargs


# ── Test tool mapping ──

class TestToolMapping:
    """Test tool name mapping between managed agent and PraisonAI."""

    def test_map_known_tools(self):
        from praisonai.integrations.managed_agents import map_managed_tools

        result = map_managed_tools(["bash", "read", "write"])
        assert result == ["execute_command", "read_file", "write_file"]

    def test_map_unknown_tools_pass_through(self):
        from praisonai.integrations.managed_agents import map_managed_tools

        result = map_managed_tools(["custom_tool"])
        assert result == ["custom_tool"]

    def test_map_empty_list(self):
        from praisonai.integrations.managed_agents import map_managed_tools

        result = map_managed_tools([])
        assert result == []
