"""
Tests for E2BManagedAgent implementation.

Tests the E2B managed runtime implementation without requiring live E2B API access.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from praisonai.integrations.managed_e2b import E2BManagedAgent, E2BManagedConfig


class TestE2BManagedConfig:
    """Test E2BManagedConfig dataclass."""
    
    def test_default_config(self):
        """Default config should have sensible defaults."""
        config = E2BManagedConfig()
        
        assert config.api_key is None  # Should be resolved from env
        assert config.template == "praisonai-agent"
        assert config.timeout == 300
        assert config.auto_shutdown is True
        assert config.idle_timeout == 600
        assert config.region == "us-east-1"
        assert config.metadata == {}
    
    def test_custom_config(self):
        """Should support custom configuration."""
        config = E2BManagedConfig(
            api_key="test-key",
            template="custom-template",
            timeout=600,
            auto_shutdown=False,
            idle_timeout=1200,
            region="eu-west-1",
            metadata={"custom": "value"}
        )
        
        assert config.api_key == "test-key"
        assert config.template == "custom-template"
        assert config.timeout == 600
        assert config.auto_shutdown is False
        assert config.idle_timeout == 1200
        assert config.region == "eu-west-1"
        assert config.metadata == {"custom": "value"}


class TestE2BManagedAgent:
    """Test E2BManagedAgent implementation."""
    
    def test_init_with_config(self):
        """Should initialize with provided config."""
        config = E2BManagedConfig(api_key="test-key")
        agent = E2BManagedAgent(config=config)
        
        assert agent.config.api_key == "test-key"
        assert agent._e2b is None  # Lazy loaded
    
    def test_init_with_kwargs(self):
        """Should support kwargs override."""
        agent = E2BManagedAgent(api_key="test-key", timeout=600)
        
        assert agent.config.api_key == "test-key"
        assert agent.config.timeout == 600
    
    @patch.dict('os.environ', {'E2B_API_KEY': 'env-test-key'})
    def test_init_with_env_key(self):
        """Should resolve API key from environment."""
        agent = E2BManagedAgent()
        
        assert agent.config.api_key == "env-test-key"
    
    def test_init_no_api_key(self):
        """Should raise error if no API key available."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="E2B API key required"):
                E2BManagedAgent()
    
    @patch('praisonai.integrations.managed_e2b.E2BManagedAgent._get_e2b')
    def test_lazy_e2b_import(self, mock_get_e2b):
        """Should lazy import E2B SDK."""
        mock_e2b = MagicMock()
        mock_get_e2b.return_value = mock_e2b
        
        agent = E2BManagedAgent(api_key="test-key")
        e2b = agent._get_e2b()
        
        mock_get_e2b.assert_called_once()
        assert e2b == mock_e2b
    
    @patch('builtins.__import__')
    def test_e2b_import_error(self, mock_import):
        """Should raise helpful error if E2B SDK not installed."""
        mock_import.side_effect = ImportError("No module named 'e2b'")
        
        agent = E2BManagedAgent(api_key="test-key")
        
        with pytest.raises(ImportError, match="E2B SDK required"):
            agent._get_e2b()
    
    @pytest.mark.asyncio
    async def test_agent_crud(self):
        """Test agent CRUD operations."""
        agent = E2BManagedAgent(api_key="test-key")
        
        # Create agent
        agent_id = await agent.create_agent({
            "name": "test-agent",
            "model": "gpt-4o",
            "system": "You are helpful."
        })
        
        assert agent_id.startswith("agent-")
        assert len(agent._agents) == 1
        
        # Retrieve agent
        retrieved = await agent.retrieve_agent(agent_id)
        assert retrieved["name"] == "test-agent"
        assert retrieved["model"] == "gpt-4o"
        assert retrieved["system"] == "You are helpful."
        
        # Update agent
        version = await agent.update_agent(agent_id, {"model": "gpt-4o-mini"})
        assert version == "2"
        
        updated = await agent.retrieve_agent(agent_id)
        assert updated["model"] == "gpt-4o-mini"
        assert updated["version"] == 2
        
        # List agents
        agents = await agent.list_agents()
        assert len(agents) == 1
        
        # Archive agent
        await agent.archive_agent(agent_id)
        archived = await agent.retrieve_agent(agent_id)
        assert archived["archived"] is True
    
    @pytest.mark.asyncio
    async def test_environment_crud(self):
        """Test environment CRUD operations."""
        agent = E2BManagedAgent(api_key="test-key")
        
        # Create environment
        env_id = await agent.create_environment({
            "name": "test-env",
            "packages": {"pip": ["pandas"]}
        })
        
        assert env_id.startswith("env-")
        
        # Retrieve environment
        retrieved = await agent.retrieve_environment(env_id)
        assert retrieved["name"] == "test-env"
        assert retrieved["packages"]["pip"] == ["pandas"]
        
        # List environments
        envs = await agent.list_environments()
        assert len(envs) == 1
        
        # Archive and delete
        await agent.archive_environment(env_id)
        await agent.delete_environment(env_id)
        
        with pytest.raises(ValueError, match="not found"):
            await agent.retrieve_environment(env_id)
    
    @pytest.mark.asyncio
    async def test_session_crud_no_e2b(self):
        """Test session operations fail gracefully without E2B."""
        agent = E2BManagedAgent(api_key="test-key")
        
        # Create dependencies
        agent_id = await agent.create_agent({"name": "test"})
        env_id = await agent.create_environment({"name": "test"})
        
        # Should fail to create session without E2B SDK
        with patch.object(agent, '_get_e2b', side_effect=ImportError("No E2B")):
            with pytest.raises(ImportError):
                await agent.create_session(agent_id, env_id)


class TestE2BProtocolConformance:
    """Test E2BManagedAgent conforms to ManagedRuntimeProtocol."""
    
    def test_protocol_conformance(self):
        """E2BManagedAgent should satisfy ManagedRuntimeProtocol."""
        from praisonaiagents.managed.protocols import ManagedRuntimeProtocol
        
        agent = E2BManagedAgent(api_key="test-key")
        assert isinstance(agent, ManagedRuntimeProtocol)


@pytest.mark.integration
class TestE2BIntegration:
    """Integration tests requiring real E2B API key."""
    
    @pytest.mark.skipif(
        not pytest.importorskip("e2b", reason="E2B SDK not available") or 
        not pytest.os.environ.get("E2B_API_KEY"),
        reason="E2B_API_KEY not set"
    )
    @pytest.mark.asyncio
    async def test_real_e2b_session(self):
        """Test creating real E2B session (requires API key)."""
        agent = E2BManagedAgent()  # Uses E2B_API_KEY from env
        
        # Create agent and environment
        agent_id = await agent.create_agent({
            "name": "integration-test",
            "model": "gpt-4o-mini",
            "system": "You are a test assistant."
        })
        
        env_id = await agent.create_environment({
            "name": "test-env",
            "packages": {"pip": ["requests"]}
        })
        
        try:
            # Create session (this will provision real E2B sandbox)
            session_id = await agent.create_session(agent_id, env_id)
            assert session_id.startswith("session-")
            
            # Verify session was created
            session = await agent.retrieve_session(session_id)
            assert session["status"] == "running"
            assert "sandbox_id" in session
            
            # Send a test event
            await agent.send_event(session_id, {
                "type": "user.message",
                "content": "Hello, test message"
            })
            
            # Should be able to stream at least one event
            event_count = 0
            async for event in agent.stream_events(session_id):
                event_count += 1
                assert "type" in event
                assert "timestamp" in event
                if event_count >= 1:  # Just verify we get at least one event
                    break
            
            assert event_count > 0
            
        finally:
            # Cleanup
            try:
                await agent.archive_session(session_id)
            except:
                pass  # Best effort cleanup