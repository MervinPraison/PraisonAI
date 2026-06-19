"""
Unit tests for turn-time runtime resolution functionality.

This test suite validates the core functionality described in issue #1938:
- Turn-time runtime resolution for handoffs and sub-agents
- Proper cache behavior and session isolation
- Fallback mechanisms when resolution fails
- Construction-time vs turn-time resolution differences
"""

import pytest
import time
import asyncio
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Dict

from .resolve import (
    resolve_runtime, 
    SessionContext,
    RuntimeProtocol,
    AgentRuntimeProtocol,
    DefaultRuntimeResolver,
    LLMRuntimeWrapper,
    FallbackRuntime,
    get_runtime_cache,
    clear_runtime_cache,
    set_global_resolver
)


class TestSessionContext:
    """Test SessionContext creation and validation."""
    
    def test_session_context_creation(self):
        """Test basic SessionContext creation."""
        session_ctx = SessionContext(
            session_id="test_session",
            timestamp=1234567890.0,
            parent_agent_id="parent_agent",
            handoff_depth=2
        )
        
        assert session_ctx.session_id == "test_session"
        assert session_ctx.timestamp == 1234567890.0
        assert session_ctx.parent_agent_id == "parent_agent"
        assert session_ctx.handoff_depth == 2
    
    def test_session_context_auto_timestamp(self):
        """Test automatic timestamp generation."""
        before = time.time()
        session_ctx = SessionContext(
            session_id="test_session",
            timestamp=0  # Should be auto-set
        )
        after = time.time()
        
        assert before <= session_ctx.timestamp <= after


class TestRuntimeResolvers:
    """Test runtime resolver implementations."""
    
    def test_default_resolver_supports_model(self):
        """Test DefaultRuntimeResolver model support detection."""
        resolver = DefaultRuntimeResolver()
        
        # Test supported models
        assert resolver.supports_model("gpt-4o")
        assert resolver.supports_model("claude-3-sonnet")
        assert resolver.supports_model("gpt-3.5-turbo")
        
        # Test unsupported models
        assert not resolver.supports_model("unknown-model")
        assert not resolver.supports_model("invalid")
    
    @patch('praisonaiagents.llm.llm.LLM')
    def test_default_resolver_with_llm(self, mock_llm_class):
        """Test DefaultRuntimeResolver when LLM class is available."""
        mock_llm = Mock()
        mock_llm_class.return_value = mock_llm
        
        resolver = DefaultRuntimeResolver()
        session_ctx = SessionContext(session_id="test", timestamp=time.time())
        
        runtime = resolver.resolve("agent1", "gpt-4o", session_ctx)
        
        assert isinstance(runtime, LLMRuntimeWrapper)
        assert runtime.model_ref == "gpt-4o"
        mock_llm_class.assert_called_once_with(model="gpt-4o")
    
    @patch('praisonaiagents.runtime.resolve.LLM', side_effect=ImportError("LLM not available"))
    def test_default_resolver_fallback(self, mock_llm_class):
        """Test DefaultRuntimeResolver fallback when LLM is not available."""
        resolver = DefaultRuntimeResolver()
        session_ctx = SessionContext(session_id="test", timestamp=time.time())
        
        runtime = resolver.resolve("agent1", "gpt-4o", session_ctx)
        
        assert isinstance(runtime, FallbackRuntime)
        assert runtime.model_ref == "gpt-4o"
        assert runtime.provider == "fallback"


class TestRuntimeWrappers:
    """Test runtime wrapper implementations."""
    
    def test_llm_runtime_wrapper(self):
        """Test LLMRuntimeWrapper functionality."""
        mock_llm = Mock()
        mock_llm.chat.return_value = "Hello response"
        
        wrapper = LLMRuntimeWrapper(
            llm=mock_llm,
            model_ref="gpt-4o", 
            agent_id="test_agent"
        )
        
        assert wrapper.model_ref == "gpt-4o"
        assert wrapper.provider == "openai"  # inferred from model name
        assert wrapper.supports_streaming == hasattr(mock_llm, 'stream')
        assert wrapper.supports_tools == True
        
        # Test sync execution
        result = wrapper.execute("Hello", temperature=0.7)
        assert result == "Hello response"
        mock_llm.chat.assert_called_once_with("Hello", temperature=0.7)
    
    @pytest.mark.asyncio
    async def test_llm_runtime_wrapper_async(self):
        """Test LLMRuntimeWrapper async functionality."""
        mock_llm = Mock()
        mock_llm.achat = Mock(return_value=asyncio.Future())
        mock_llm.achat.return_value.set_result("Async response")
        
        wrapper = LLMRuntimeWrapper(
            llm=mock_llm,
            model_ref="claude-3-sonnet",
            agent_id="test_agent" 
        )
        
        assert wrapper.provider == "anthropic"  # inferred from model name
        
        # Test async execution
        result = await wrapper.aexecute("Hello async", temperature=0.5)
        assert result == "Async response"
        mock_llm.achat.assert_called_once_with("Hello async", temperature=0.5)
    
    @pytest.mark.asyncio  
    async def test_llm_runtime_wrapper_async_fallback(self):
        """Test LLMRuntimeWrapper async fallback to sync execution."""
        mock_llm = Mock()
        mock_llm.chat.return_value = "Sync response"
        # No achat method - should fall back to sync in executor
        
        wrapper = LLMRuntimeWrapper(
            llm=mock_llm,
            model_ref="gpt-4",
            agent_id="test_agent"
        )
        
        result = await wrapper.aexecute("Hello", param="value")
        assert result == "Sync response"
        mock_llm.chat.assert_called_once_with("Hello", param="value")
    
    def test_fallback_runtime(self):
        """Test FallbackRuntime implementation."""
        runtime = FallbackRuntime(model_ref="unknown-model", agent_id="test_agent")
        
        assert runtime.model_ref == "unknown-model"
        assert runtime.provider == "fallback"
        assert runtime.supports_streaming == False
        assert runtime.supports_tools == False
        
        # FallbackRuntime should now raise RuntimeError instead of returning stubs
        with pytest.raises(RuntimeError, match="No LLM runtime available"):
            runtime.execute("Test prompt")
    
    @pytest.mark.asyncio
    async def test_fallback_runtime_async(self):
        """Test FallbackRuntime async implementation."""
        runtime = FallbackRuntime(model_ref="unknown-model", agent_id="test_agent")
        
        # FallbackRuntime should now raise RuntimeError instead of returning stubs
        with pytest.raises(RuntimeError, match="No LLM runtime available"):
            await runtime.aexecute("Test async prompt")


class TestRuntimeResolution:
    """Test core runtime resolution functionality."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_runtime_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_runtime_cache()
    
    @patch('praisonaiagents.runtime.resolve.get_global_resolver')
    def test_resolve_runtime_success(self, mock_get_resolver):
        """Test successful runtime resolution."""
        # Setup mock resolver
        mock_runtime = Mock(spec=AgentRuntimeProtocol)
        mock_runtime.model_ref = "gpt-4o"
        mock_runtime.provider = "openai"
        
        mock_resolver = Mock()
        mock_resolver.supports_model.return_value = True
        mock_resolver.resolve.return_value = mock_runtime
        mock_get_resolver.return_value = mock_resolver
        
        # Test resolution
        session_ctx = SessionContext(session_id="test_session", timestamp=time.time())
        result = resolve_runtime("agent1", "gpt-4o", session_ctx)
        
        assert result == mock_runtime
        mock_resolver.supports_model.assert_called_once_with("gpt-4o")
        mock_resolver.resolve.assert_called_once_with("agent1", "gpt-4o", session_ctx)
    
    @patch('praisonaiagents.runtime.resolve.get_global_resolver')
    def test_resolve_runtime_unsupported_model(self, mock_get_resolver):
        """Test runtime resolution with unsupported model."""
        mock_resolver = Mock()
        mock_resolver.supports_model.return_value = False
        mock_get_resolver.return_value = mock_resolver
        
        session_ctx = SessionContext(session_id="test_session", timestamp=time.time())
        
        with pytest.raises(RuntimeError, match="No runtime resolver available for model: unsupported-model"):
            resolve_runtime("agent1", "unsupported-model", session_ctx)
    
    @patch('praisonaiagents.runtime.resolve.get_global_resolver')
    def test_resolve_runtime_resolver_failure(self, mock_get_resolver):
        """Test runtime resolution when resolver fails.""" 
        mock_resolver = Mock()
        mock_resolver.supports_model.return_value = True
        mock_resolver.resolve.side_effect = Exception("Resolver failed")
        mock_get_resolver.return_value = mock_resolver
        
        session_ctx = SessionContext(session_id="test_session", timestamp=time.time())
        
        with pytest.raises(RuntimeError, match="Runtime resolution failed for model gpt-4o: Resolver failed"):
            resolve_runtime("agent1", "gpt-4o", session_ctx)


class TestRuntimeCaching:
    """Test runtime caching behavior."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_runtime_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_runtime_cache()
    
    @patch('praisonaiagents.runtime.resolve.get_global_resolver')  
    def test_runtime_caching(self, mock_get_resolver):
        """Test that runtime resolution results are cached."""
        mock_runtime = Mock(spec=AgentRuntimeProtocol)
        mock_resolver = Mock()
        mock_resolver.supports_model.return_value = True
        mock_resolver.resolve.return_value = mock_runtime
        mock_get_resolver.return_value = mock_resolver
        
        session_ctx = SessionContext(session_id="cache_test", timestamp=time.time())
        
        # First call should resolve
        result1 = resolve_runtime("agent1", "gpt-4o", session_ctx)
        assert result1 == mock_runtime
        assert mock_resolver.resolve.call_count == 1
        
        # Second call should use cache  
        result2 = resolve_runtime("agent1", "gpt-4o", session_ctx)
        assert result2 == mock_runtime
        assert mock_resolver.resolve.call_count == 1  # No additional calls
    
    @patch('praisonaiagents.runtime.resolve.get_global_resolver')
    @patch('praisonaiagents.runtime.resolve._cache_ttl_seconds', 0.1)  # Short TTL for testing
    def test_cache_expiration(self, mock_get_resolver):
        """Test that cache entries expire after TTL."""
        mock_runtime = Mock(spec=AgentRuntimeProtocol)
        mock_resolver = Mock()
        mock_resolver.supports_model.return_value = True  
        mock_resolver.resolve.return_value = mock_runtime
        mock_get_resolver.return_value = mock_resolver
        
        session_ctx = SessionContext(session_id="expire_test", timestamp=time.time())
        
        # First call
        resolve_runtime("agent1", "gpt-4o", session_ctx)
        assert mock_resolver.resolve.call_count == 1
        
        # Wait for cache to expire
        time.sleep(0.2)
        
        # Second call after expiration should resolve again
        resolve_runtime("agent1", "gpt-4o", session_ctx)
        assert mock_resolver.resolve.call_count == 2
    
    def test_cache_session_isolation(self):
        """Test that cache is isolated between sessions."""
        # This test uses the real resolver since we're testing isolation
        session_ctx1 = SessionContext(session_id="session1", timestamp=time.time())
        session_ctx2 = SessionContext(session_id="session2", timestamp=time.time())
        
        # Cache for session1
        runtime1 = resolve_runtime("agent1", "gpt-4o", session_ctx1) 
        
        # Cache for session2 should be separate
        runtime2 = resolve_runtime("agent1", "gpt-4o", session_ctx2)
        
        # Should be different instances due to separate sessions
        cache = get_runtime_cache()
        assert "session1" in cache
        assert "session2" in cache
        assert len(cache["session1"]) == 1
        assert len(cache["session2"]) == 1
    
    def test_clear_cache_all(self):
        """Test clearing all cache.""" 
        session_ctx1 = SessionContext(session_id="session1", timestamp=time.time())
        session_ctx2 = SessionContext(session_id="session2", timestamp=time.time())
        
        # Add entries to cache
        resolve_runtime("agent1", "gpt-4o", session_ctx1)
        resolve_runtime("agent1", "gpt-4o", session_ctx2)
        
        cache = get_runtime_cache()
        assert len(cache) == 2
        
        # Clear all cache
        clear_runtime_cache()
        
        cache = get_runtime_cache()
        assert len(cache) == 0
    
    def test_clear_cache_specific_session(self):
        """Test clearing cache for specific session."""
        session_ctx1 = SessionContext(session_id="session1", timestamp=time.time())
        session_ctx2 = SessionContext(session_id="session2", timestamp=time.time())
        
        # Add entries to cache
        resolve_runtime("agent1", "gpt-4o", session_ctx1)
        resolve_runtime("agent1", "gpt-4o", session_ctx2)
        
        cache = get_runtime_cache()
        assert len(cache) == 2
        
        # Clear specific session
        clear_runtime_cache("session1")
        
        cache = get_runtime_cache()
        assert len(cache) == 1
        assert "session2" in cache
        assert "session1" not in cache


class TestConstructionTimeVsTurnTime:
    """
    Test the difference between construction-time and turn-time resolution.
    
    This validates the core issue addressed by #1938 - ensuring that handoffs
    and sub-agents don't inherit construction-time runtime pins.
    """
    
    def test_construction_time_pin_problem(self):
        """
        Test demonstrates the problem: construction-time pins don't adapt to model changes.
        
        This test simulates the issue where an agent is constructed with one model
        but then switches models, yet handoffs still use the construction-time model.
        """
        # Simulate construction-time behavior (before fix)
        construction_time_model = "gpt-3.5-turbo"
        session_ctx = SessionContext(session_id="construction_test", timestamp=time.time())
        
        # Agent constructed with initial model
        construction_runtime = resolve_runtime("agent1", construction_time_model, session_ctx)
        
        # Agent model changes at runtime (router decision, user preference, etc.)
        runtime_model = "gpt-4o"
        
        # Turn-time resolution should use the NEW model, not construction-time pin
        turn_time_runtime = resolve_runtime("agent1", runtime_model, session_ctx)
        
        # The runtimes should be different (addressing the core issue)
        assert construction_runtime.model_ref == "gpt-3.5-turbo"
        assert turn_time_runtime.model_ref == "gpt-4o"
        assert construction_runtime.model_ref != turn_time_runtime.model_ref
    
    def test_turn_time_model_switching(self):
        """Test that turn-time resolution properly handles model switching."""
        session_ctx = SessionContext(session_id="model_switch_test", timestamp=time.time())
        
        # First call with model A
        runtime_a = resolve_runtime("agent1", "gpt-4o", session_ctx)
        assert runtime_a.model_ref == "gpt-4o"
        
        # Second call with model B (should get different runtime)  
        runtime_b = resolve_runtime("agent1", "claude-3-sonnet", session_ctx)
        assert runtime_b.model_ref == "claude-3-sonnet"
        
        # Verify they are cached separately
        cache = get_runtime_cache()
        session_cache = cache[session_ctx.session_id]
        assert len(session_cache) == 2  # Two different cache entries
        
        # Keys should be different due to different models
        cache_keys = list(session_cache.keys())
        assert any("gpt-4o" in key for key in cache_keys)
        assert any("claude-3-sonnet" in key for key in cache_keys)


# Integration test with handoff simulation
class MockAgent:
    """Mock agent for testing handoff scenarios."""
    
    def __init__(self, name, model="gpt-4o", agent_id=None):
        self.name = name
        self.llm = model
        self.model = model
        self.agent_id = agent_id or name
        self._session_id = "test_session"
    
    def chat(self, prompt, **kwargs):
        return f"Response from {self.name} using {self.model}: {prompt}"


class TestHandoffIntegration:
    """Test integration with handoff scenarios."""
    
    def test_handoff_runtime_resolution_simulation(self):
        """
        Simulate handoff scenario to verify turn-time resolution.
        
        This test simulates the scenario described in issue #1938 where
        a handoff should use the target agent's current model, not a
        construction-time pin.
        """
        # Create source and target agents with different models
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo") 
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        session_ctx = SessionContext(
            session_id="handoff_test",
            timestamp=time.time(),
            parent_agent_id=source_agent.name,
            handoff_depth=1
        )
        
        # Resolve runtime for target agent (simulating handoff)
        target_runtime = resolve_runtime(
            target_agent.agent_id,
            target_agent.llm, 
            session_ctx
        )
        
        # Verify correct model is resolved
        assert target_runtime.model_ref == "gpt-4o"
        
        # Target agent changes model mid-conversation
        target_agent.llm = "claude-3-sonnet"
        target_agent.model = "claude-3-sonnet"
        
        # New handoff should use updated model (turn-time resolution)
        updated_runtime = resolve_runtime(
            target_agent.agent_id,
            target_agent.llm,
            session_ctx
        )
        
        assert updated_runtime.model_ref == "claude-3-sonnet"
        assert updated_runtime.model_ref != target_runtime.model_ref
        
        # Verify cache has both entries
        cache = get_runtime_cache()
        session_cache = cache[session_ctx.session_id] 
        assert len(session_cache) == 2


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])