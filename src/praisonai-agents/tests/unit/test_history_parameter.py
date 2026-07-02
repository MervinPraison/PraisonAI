"""
Unit tests for history injection via memory presets.

History is enabled via:
- memory="history" preset (10 messages)
- memory="chat" preset (20 messages)
- memory=MemoryConfig(history=True, history_limit=N)

The history= parameter and HistoryConfig class have been removed
to keep the API simple and consistent with other memory presets.
"""

import pytest
from unittest.mock import Mock


class TestDefaultHistoryDisabled:
    """Test that history is disabled by default."""
    
    def test_default_history_disabled(self):
        """Agent() without memory should have history disabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent"
        )
        
        assert agent._history_enabled is False
    
    def test_memory_true_does_not_enable_history(self):
        """Agent(memory=True) should NOT enable history by default."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory=True
        )
        
        # memory=True enables memory backend, not history injection
        assert agent._history_enabled is False


class TestMemoryHistoryPreset:
    """Test memory='history' preset."""
    
    def test_memory_history_preset_exists(self):
        """memory='history' should be a valid preset."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        assert "history" in MEMORY_PRESETS
    
    def test_memory_history_enables_history(self):
        """Agent(memory='history') should enable history injection."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory="history"
        )
        
        # Memory should be enabled
        assert agent.memory is not None or agent._memory_instance is not None
        # History should be enabled
        assert agent._history_enabled is True
    
    def test_memory_session_preset_exists(self):
        """memory='session' should be a valid preset (alias for history)."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        assert "session" in MEMORY_PRESETS
    
    def test_memory_chat_preset_exists(self):
        """memory='chat' should be a valid preset for conversational use."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        assert "chat" in MEMORY_PRESETS


class TestMemoryConfigHistoryFields:
    """Test new history fields in MemoryConfig."""
    
    def test_memory_config_has_history_field(self):
        """MemoryConfig should have a history field."""
        from praisonaiagents.config import MemoryConfig
        
        config = MemoryConfig(history=True)
        assert config.history is True
    
    def test_memory_config_has_history_limit_field(self):
        """MemoryConfig should have a history_limit field."""
        from praisonaiagents.config import MemoryConfig
        
        config = MemoryConfig(history=True, history_limit=20)
        assert config.history_limit == 20
    
    def test_memory_config_history_defaults(self):
        """MemoryConfig history fields should have sensible defaults."""
        from praisonaiagents.config import MemoryConfig
        
        config = MemoryConfig()
        assert config.history is False  # Disabled by default
        assert config.history_limit == 10  # Default limit
    
    def test_agent_memory_config_with_history(self):
        """Agent with MemoryConfig(history=True) should enable history."""
        from praisonaiagents import Agent
        from praisonaiagents.config import MemoryConfig
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory=MemoryConfig(history=True, history_limit=15)
        )
        
        assert agent._history_enabled is True
        assert agent._history_limit == 15


class TestHistoryInjection:
    """Test that history is actually injected into messages."""
    
    def test_history_injected_into_messages(self):
        """When memory='history', session history should be in messages."""
        from praisonaiagents import Agent
        
        # Create agent with history enabled via preset
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory="history"
        )
        
        # Set _using_custom_llm to bypass OpenAI client initialization
        agent._using_custom_llm = True
        
        # Mock session store with some history
        mock_store = Mock()
        mock_store.get_chat_history.return_value = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]
        agent._session_store = mock_store
        agent._history_session_id = "test-session"
        
        # Build messages
        messages, _ = agent._build_messages("New question")
        
        # Should contain the injected history
        message_contents = [m.get("content", "") for m in messages]
        assert "Previous question" in str(message_contents)
        assert "Previous answer" in str(message_contents)
    
    def test_history_respects_limit(self):
        """History injection should respect the limit from MemoryConfig."""
        from praisonaiagents import Agent
        from praisonaiagents.config import MemoryConfig
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            memory=MemoryConfig(history=True, history_limit=2)
        )
        
        # Set _using_custom_llm to bypass OpenAI client initialization
        agent._using_custom_llm = True
        
        # Mock session store
        mock_store = Mock()
        mock_store.get_chat_history.return_value = [
            {"role": "user", "content": "Msg 1"},
            {"role": "assistant", "content": "Msg 2"}
        ]
        agent._session_store = mock_store
        agent._history_session_id = "test-session"
        
        # Build messages
        agent._build_messages("New question")
        
        # Should have called with limit=2
        mock_store.get_chat_history.assert_called_with("test-session", max_messages=2)


class TestHistoryWithSession:
    """Test history integration with session management."""
    
    def test_history_uses_auto_save_session(self):
        """If auto_save is set, history should use that session."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            auto_save="my-auto-session",
            memory="history"
        )
        
        # Should use auto_save session for history
        assert agent._history_session_id == "my-auto-session"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
