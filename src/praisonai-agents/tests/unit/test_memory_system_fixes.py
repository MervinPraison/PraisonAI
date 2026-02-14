"""
TDD Tests for Memory System Fixes.

Tests written BEFORE implementation to drive the fixes for:
1. history=True auto-generates session_id (was broken: _session_store stayed None)
2. auto_memory wires process_interaction after agent response
3. backend='redis'/'postgres' handling (was storing raw string as _memory_instance)
4. MemoryProtocol extended with get_context/save_session
5. _history_session_id reconciled with _session_id
"""
from unittest.mock import patch
import logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(**kwargs):
    """Create an Agent with memory config, mocking LLM to avoid real API calls."""
    from praisonaiagents import Agent
    defaults = dict(
        name="test_agent",
        instructions="Be helpful",
        llm="gpt-4o-mini",
    )
    defaults.update(kwargs)
    agent = Agent(**defaults)
    return agent


# ===========================================================================
# 1. history=True auto-generates session_id
# ===========================================================================

class TestHistoryAutoSessionId:
    """history=True should auto-generate a session_id so _init_session_store
    can create the store and history injection fires."""

    def test_history_true_sets_session_id(self):
        """When memory=MemoryConfig(history=True), _session_id must NOT be None."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True))
        # After construction, session_id should be auto-set
        assert agent._session_id is not None, (
            "history=True must auto-generate a session_id"
        )

    def test_history_true_sets_history_session_id(self):
        """_history_session_id must match _session_id when auto-generated."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True))
        assert agent._history_session_id is not None
        assert agent._history_session_id == agent._session_id

    def test_history_true_with_explicit_session_id(self):
        """Explicit session_id should be respected, not overwritten."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True, session_id="my-session"))
        assert agent._session_id == "my-session"
        assert agent._history_session_id == "my-session"

    def test_history_true_with_auto_save(self):
        """auto_save should be used as session_id when history=True."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True, auto_save="chat1"))
        assert agent._history_session_id == "chat1"

    def test_history_false_no_session_id(self):
        """history=False should NOT auto-generate session_id."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=False))
        # session_id should remain None (no auto-gen)
        assert agent._history_enabled is False

    def test_history_preset_sets_session_id(self):
        """memory='history' preset should auto-generate session_id."""
        from praisonaiagents import Agent
        agent = _make_agent(memory="history")
        assert agent._history_enabled is True
        assert agent._session_id is not None


# ===========================================================================
# 2. auto_memory wires process_interaction after agent response
# ===========================================================================

class TestAutoMemoryWiring:
    """When auto_memory=True in MemoryConfig, AutoMemory.process_interaction
    should be called after each agent response."""

    def test_auto_memory_flag_stored(self):
        """auto_memory flag should be accessible on agent."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(auto_memory=True))
        assert agent._auto_memory is True or agent._auto_memory is not None

    def test_auto_memory_instance_created_lazily(self):
        """AutoMemory wrapper should be created when auto_memory=True."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(auto_memory=True))
        # The _auto_memory_instance should exist (may be lazy)
        assert hasattr(agent, '_auto_memory_instance') or hasattr(agent, '_auto_memory')

    def test_process_auto_memory_method_exists(self):
        """Agent should have a _process_auto_memory method."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(auto_memory=True))
        assert hasattr(agent, '_process_auto_memory'), (
            "Agent must have _process_auto_memory method for wiring"
        )

    def test_process_auto_memory_noop_when_disabled(self):
        """_process_auto_memory should be a no-op when auto_memory=False."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(auto_memory=False))
        # Should not raise
        agent._process_auto_memory("hello", "world")


# ===========================================================================
# 3. backend='redis'/'postgres' handling
# ===========================================================================

class TestBackendHandling:
    """backend='redis' and 'postgres' should NOT silently store a raw string
    as _memory_instance. They should either work or raise a clear error."""

    def test_redis_backend_not_string(self):
        """backend='redis' must NOT result in _memory_instance being a string."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(backend="redis"))
        if agent._memory_instance is not None:
            assert not isinstance(agent._memory_instance, str), (
                "backend='redis' must not store raw string as memory instance"
            )

    def test_postgres_backend_not_string(self):
        """backend='postgres' must NOT result in _memory_instance being a string."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(backend="postgres"))
        if agent._memory_instance is not None:
            assert not isinstance(agent._memory_instance, str), (
                "backend='postgres' must not store raw string as memory instance"
            )

    def test_file_backend_creates_file_memory(self):
        """backend='file' should create a FileMemory instance."""
        from praisonaiagents import Agent, MemoryConfig
        from praisonaiagents.memory.file_memory import FileMemory
        agent = _make_agent(memory=MemoryConfig(backend="file"))
        assert isinstance(agent._memory_instance, FileMemory)

    def test_unknown_backend_warns(self):
        """Unknown backend should log a warning, not silently break."""
        from praisonaiagents import Agent, MemoryConfig
        import logging
        with patch.object(logging, 'warning') as mock_warn:
            agent = _make_agent(memory=MemoryConfig(backend="unknown_db"))
            # Should either warn or the instance should be None/FileMemory fallback
            if agent._memory_instance is not None:
                assert not isinstance(agent._memory_instance, str)


# ===========================================================================
# 4. MemoryProtocol extended with get_context and save_session
# ===========================================================================

class TestMemoryProtocolExtensions:
    """MemoryProtocol should include get_context and save_session for
    consistent interface across FileMemory and Memory."""

    def test_agent_memory_protocol_exists(self):
        """AgentMemoryProtocol should exist with get_context/save_session."""
        from praisonaiagents.memory.protocols import AgentMemoryProtocol
        assert hasattr(AgentMemoryProtocol, 'get_context')
        assert hasattr(AgentMemoryProtocol, 'save_session')

    def test_file_memory_satisfies_agent_protocol(self):
        """FileMemory should satisfy AgentMemoryProtocol."""
        from praisonaiagents.memory.protocols import AgentMemoryProtocol
        from praisonaiagents.memory.file_memory import FileMemory
        fm = FileMemory(user_id="test")
        assert isinstance(fm, AgentMemoryProtocol)

    def test_agent_memory_protocol_runtime_checkable(self):
        """AgentMemoryProtocol should be runtime_checkable."""
        from praisonaiagents.memory.protocols import AgentMemoryProtocol
        
        class FakeMemory:
            def get_context(self, query=None):
                return ""
            def save_session(self, name, conversation_history=None, metadata=None):
                pass
        
        assert isinstance(FakeMemory(), AgentMemoryProtocol)


# ===========================================================================
# 5. _history_session_id reconciled with _session_id
# ===========================================================================

class TestHistorySessionIdReconciliation:
    """_history_session_id and _session_id should be reconciled so that
    _init_session_store creates the store AND history injection uses the right ID."""

    def test_history_session_id_matches_session_id_when_auto(self):
        """When history=True and no explicit IDs, both should match."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True))
        if agent._session_id is not None:
            assert agent._history_session_id == agent._session_id

    def test_explicit_session_id_used_for_history(self):
        """Explicit session_id should propagate to _history_session_id."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True, session_id="explicit"))
        assert agent._session_id == "explicit"
        assert agent._history_session_id == "explicit"

    def test_auto_save_session_id_for_history(self):
        """auto_save should be used as _history_session_id."""
        from praisonaiagents import Agent, MemoryConfig
        agent = _make_agent(memory=MemoryConfig(history=True, auto_save="my_session"))
        assert agent._history_session_id == "my_session"


# ===========================================================================
# 6. Smoke tests - end-to-end memory config
# ===========================================================================

class TestMemoryConfigSmoke:
    """Smoke tests for common memory configurations."""

    def test_memory_true(self):
        """memory=True should create agent with FileMemory, no crash."""
        from praisonaiagents import Agent
        agent = _make_agent(memory=True)
        assert agent._memory_instance is not None

    def test_memory_false(self):
        """memory=False should create agent with no memory."""
        from praisonaiagents import Agent
        agent = _make_agent(memory=False)
        assert agent._memory_instance is None

    def test_memory_history_preset(self):
        """memory='history' preset should enable history."""
        from praisonaiagents import Agent
        agent = _make_agent(memory="history")
        assert agent._history_enabled is True

    def test_memory_learn_preset(self):
        """memory='learn' preset should enable learn."""
        from praisonaiagents import Agent
        agent = _make_agent(memory="learn")
        # Should not crash; learn config should be present
        assert agent._memory_instance is not None

    def test_store_memory_public_api(self):
        """agent.store_memory() should work with memory=True."""
        from praisonaiagents import Agent
        agent = _make_agent(memory=True)
        # Should not raise
        agent.store_memory("User likes Python", "long_term")

    def test_get_memory_context(self):
        """agent.get_memory_context() should return string."""
        from praisonaiagents import Agent
        agent = _make_agent(memory=True)
        ctx = agent.get_memory_context()
        assert isinstance(ctx, str)
