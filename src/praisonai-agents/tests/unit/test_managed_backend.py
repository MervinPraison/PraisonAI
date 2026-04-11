"""
Unit tests for the managed agent backend integration.

Tests the delegation path: Agent -> execution_mixin._delegate_to_backend -> ManagedAgentIntegration.execute
Uses mocks to avoid real API calls.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


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

    def test_init_custom_config(self):
        """Config should be stored correctly."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(
            api_key="test-key",
            config={"model": "claude-sonnet-4-6"},
            instructions="Be concise.",
        )
        assert m.config["model"] == "claude-sonnet-4-6"
        assert m.instructions == "Be concise."

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
        """reset_all should clear everything."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")
        m.agent_id = "agent-123"
        m.environment_id = "env-123"
        m._session_id = "sess-123"
        m.reset_all()
        assert m.agent_id is None
        assert m.environment_id is None
        assert m._session_id is None
        assert m._client is None

    def test_execute_sync_with_mock_sdk(self):
        """_execute_sync should orchestrate create+stream correctly."""
        from praisonai.integrations.managed_agents import ManagedAgentIntegration

        m = ManagedAgentIntegration(api_key="test-key")

        # Mock the Anthropic client
        mock_client = MagicMock()

        # Mock agent creation
        mock_agent = MagicMock()
        mock_agent.id = "agent-001"
        mock_agent.version = 1
        mock_client.beta.agents.create.return_value = mock_agent

        # Mock environment creation
        mock_env = MagicMock()
        mock_env.id = "env-001"
        mock_client.beta.environments.create.return_value = mock_env

        # Mock session creation
        mock_session = MagicMock()
        mock_session.id = "sess-001"
        mock_client.beta.sessions.create.return_value = mock_session

        # Mock streaming events
        mock_event_msg = MagicMock()
        mock_event_msg.type = "agent.message"
        mock_block = MagicMock()
        mock_block.text = "Hello from managed agent!"
        mock_event_msg.content = [mock_block]

        mock_event_idle = MagicMock()
        mock_event_idle.type = "session.status_idle"

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=iter([mock_event_msg, mock_event_idle]))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_client.beta.sessions.events.stream.return_value = mock_stream_ctx

        # Mock send
        mock_client.beta.sessions.events.send = MagicMock()

        # Inject mock
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

        mock_client = MagicMock()

        # Mock streaming
        mock_event = MagicMock()
        mock_event.type = "agent.message"
        mock_block = MagicMock()
        mock_block.text = "cached response"
        mock_event.content = [mock_block]

        mock_idle = MagicMock()
        mock_idle.type = "session.status_idle"

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=iter([mock_event, mock_idle]))
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_client.beta.sessions.events.stream.return_value = mock_stream_ctx
        mock_client.beta.sessions.events.send = MagicMock()

        m._client = mock_client

        result = m._execute_sync("test")
        assert result == "cached response"
        # Should NOT create new agent/env/session
        mock_client.beta.agents.create.assert_not_called()
        mock_client.beta.environments.create.assert_not_called()
        mock_client.beta.sessions.create.assert_not_called()


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
