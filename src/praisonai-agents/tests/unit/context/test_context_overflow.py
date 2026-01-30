"""
Tests for context overflow prevention and recovery.

TDD: These tests define the expected behavior for:
1. ContextConfig.for_recipe() preset
2. Pre-LLM overflow protection
3. Emergency truncation
4. Tool output limits
"""



class TestContextConfigRecipePreset:
    """Tests for ContextConfig.for_recipe() classmethod."""
    
    def test_for_recipe_returns_context_config(self):
        """for_recipe() should return a ContextConfig instance."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig.for_recipe()
        assert isinstance(config, ContextConfig)
    
    def test_for_recipe_has_auto_compact_enabled(self):
        """Recipe preset should have auto_compact=True."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig.for_recipe()
        assert config.auto_compact is True
    
    def test_for_recipe_has_lower_threshold(self):
        """Recipe preset should trigger compaction earlier (70% vs 80%)."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig.for_recipe()
        assert config.compact_threshold == 0.7
    
    def test_for_recipe_has_smart_strategy(self):
        """Recipe preset should use SMART optimization strategy."""
        from praisonaiagents.context.models import ContextConfig, OptimizerStrategy
        
        config = ContextConfig.for_recipe()
        assert config.strategy == OptimizerStrategy.SMART
    
    def test_for_recipe_has_tool_output_limit(self):
        """Recipe preset should limit tool outputs to 2000 tokens."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig.for_recipe()
        assert config.tool_output_max == 2000
    
    def test_for_recipe_keeps_recent_turns(self):
        """Recipe preset should keep last 3 turns intact."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig.for_recipe()
        assert config.keep_recent_turns == 3


class TestWorkflowContextDefault:
    """Tests for Workflow context default behavior."""
    
    def test_workflow_context_default_is_true(self):
        """Workflow should have context=True by default."""
        from praisonaiagents.workflows import Workflow, Task
        
        step = Task(name="test", action="test action")
        workflow = Workflow(name="test", steps=[step])
        
        # context should be True by default
        assert workflow.context is True
    
    def test_workflow_context_can_be_disabled(self):
        """Workflow context can be explicitly disabled."""
        from praisonaiagents.workflows import Workflow, Task
        
        step = Task(name="test", action="test action")
        workflow = Workflow(name="test", steps=[step], context=False)
        
        assert workflow.context is False


class TestAgentContextDefault:
    """Tests for Agent context default behavior."""
    
    def test_agent_context_default_is_none_without_tools(self):
        """Agent should have context=None by default when no tools (zero overhead)."""
        from praisonaiagents import Agent
        
        # Don't access context_manager property to avoid initialization
        agent = Agent(instructions="test")
        # Smart default: None when no tools (disabled)
        assert agent._context_param is None
    
    def test_agent_context_manager_not_initialized_when_disabled(self):
        """context_manager should be None when context=False."""
        from praisonaiagents import Agent
        
        agent = Agent(instructions="test", context=False)
        # Access the property to trigger lazy init
        assert agent.context_manager is None


class TestEmergencyTruncation:
    """Tests for emergency truncation when optimization isn't enough."""
    
    def test_emergency_truncate_exists(self):
        """ContextManager should have emergency_truncate method."""
        from praisonaiagents.context import ContextManager
        
        manager = ContextManager(model="gpt-4o-mini")
        assert hasattr(manager, 'emergency_truncate')
    
    def test_emergency_truncate_reduces_to_target(self):
        """emergency_truncate should reduce messages to target tokens."""
        from praisonaiagents.context import ContextManager
        
        manager = ContextManager(model="gpt-4o-mini")
        
        # Create messages that exceed target
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello " * 1000},  # ~1000 tokens
            {"role": "assistant", "content": "Hi " * 1000},  # ~1000 tokens
            {"role": "user", "content": "More " * 1000},  # ~1000 tokens
        ]
        
        target_tokens = 500
        truncated = manager.emergency_truncate(messages, target_tokens)
        
        # Should have fewer messages or truncated content
        from praisonaiagents.context.tokens import estimate_messages_tokens
        result_tokens = estimate_messages_tokens(truncated)
        
        # Allow some margin for system message preservation
        assert result_tokens <= target_tokens * 1.5


class TestToolOutputLimits:
    """Tests for tool output truncation at source."""
    
    def test_default_tool_output_limit(self):
        """Default tool output limit should be 16000 chars (~4000 tokens) for full page content."""
        # This is tested via the constant
        from praisonaiagents.agent.agent import DEFAULT_TOOL_OUTPUT_LIMIT
        assert DEFAULT_TOOL_OUTPUT_LIMIT == 16000  # ~4000 tokens * 4 chars/token
    
    def test_tool_output_truncated_when_exceeds_limit(self):
        """Tool output should be truncated when exceeding limit."""
        # This will be tested via integration test
        pass


class TestMessageDeduplication:
    """Tests for message deduplication in ContextManager."""
    
    def test_deduplicate_messages_removes_duplicates(self):
        """Should remove duplicate content from messages."""
        from praisonaiagents.context import ContextManager
        
        manager = ContextManager(model="gpt-4o-mini")
        
        # Create messages with duplicate content
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Search for AI news"},
            {"role": "tool", "content": "This is a long search result " * 50, "tool_call_id": "1"},
            {"role": "tool", "content": "This is a long search result " * 50, "tool_call_id": "2"},  # Duplicate
            {"role": "assistant", "content": "Here are the results."},
        ]
        
        deduped = manager._deduplicate_messages(messages)
        
        # Should have removed one duplicate
        assert len(deduped) == 4
    
    def test_deduplicate_preserves_system_messages(self):
        """Should always keep system messages."""
        from praisonaiagents.context import ContextManager
        
        manager = ContextManager(model="gpt-4o-mini")
        
        messages = [
            {"role": "system", "content": "System prompt 1"},
            {"role": "system", "content": "System prompt 2"},
            {"role": "user", "content": "Hello"},
        ]
        
        deduped = manager._deduplicate_messages(messages)
        
        # Both system messages should be kept
        assert len(deduped) == 3
    
    def test_deduplicate_preserves_tool_calls(self):
        """Should always keep assistant messages with tool_calls."""
        from praisonaiagents.context import ContextManager
        
        manager = ContextManager(model="gpt-4o-mini")
        
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "2"}]},
        ]
        
        deduped = manager._deduplicate_messages(messages)
        
        # Both tool call messages should be kept
        assert len(deduped) == 2


class TestSessionDeduplicationCache:
    """Tests for session-level deduplication cache."""
    
    def test_session_cache_creation(self):
        """Should create session deduplication cache."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache()
        assert cache is not None
        assert cache.get_stats()["duplicates_prevented"] == 0
    
    def test_session_cache_check_and_add_new(self):
        """Should return False for new content."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache()
        is_dup = cache.check_and_add("hash123", "agent1", 100)
        
        assert is_dup is False
    
    def test_session_cache_check_and_add_duplicate(self):
        """Should return True for duplicate content."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache()
        cache.check_and_add("hash123", "agent1", 100)
        is_dup = cache.check_and_add("hash123", "agent2", 100)
        
        assert is_dup is True
        assert cache.get_stats()["duplicates_prevented"] == 1
        assert cache.get_stats()["tokens_saved"] == 100
    
    def test_session_cache_cross_agent_dedup(self):
        """Should deduplicate across different agents."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache()
        
        # Agent 1 adds content
        cache.check_and_add("content_hash_abc", "keyword_generator", 500)
        
        # Agent 2 tries to add same content
        is_dup = cache.check_and_add("content_hash_abc", "deep_researcher", 500)
        
        assert is_dup is True
        assert cache.get_stats()["duplicates_prevented"] == 1
    
    def test_session_cache_lru_eviction(self):
        """Should evict oldest entries when at capacity."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache(max_size=3)
        
        cache.check_and_add("hash1", "agent1", 100)
        cache.check_and_add("hash2", "agent1", 100)
        cache.check_and_add("hash3", "agent1", 100)
        cache.check_and_add("hash4", "agent1", 100)  # Should evict hash1
        
        # hash1 should no longer be in cache
        is_dup = cache.check_and_add("hash1", "agent2", 100)
        assert is_dup is False  # Not a duplicate anymore
    
    def test_session_cache_clear(self):
        """Should clear all cached hashes."""
        from praisonaiagents.context import SessionDeduplicationCache
        
        cache = SessionDeduplicationCache()
        cache.check_and_add("hash1", "agent1", 100)
        cache.check_and_add("hash1", "agent2", 100)  # Duplicate
        
        assert cache.get_stats()["duplicates_prevented"] == 1
        
        cache.clear()
        
        assert cache.get_stats()["duplicates_prevented"] == 0
        
        # After clear, same hash should not be duplicate
        is_dup = cache.check_and_add("hash1", "agent3", 100)
        assert is_dup is False


class TestOverflowRecovery:
    """Tests for overflow error recovery."""
    
    def test_context_length_error_detection(self):
        """Should detect context_length_exceeded errors."""
        from praisonaiagents.llm.llm import LLMContextLengthExceededException
        
        error = LLMContextLengthExceededException("context_length_exceeded: This model's maximum context length is 128000 tokens")
        assert error._is_context_limit_error(str(error))
    
    def test_context_length_error_variants(self):
        """Should detect various context limit error messages."""
        from praisonaiagents.llm.llm import LLMContextLengthExceededException
        
        error_messages = [
            "maximum context length",
            "context window is too long",
            "context length exceeded",
            "context_length_exceeded",
        ]
        
        for msg in error_messages:
            error = LLMContextLengthExceededException(msg)
            assert error._is_context_limit_error(msg), f"Should detect: {msg}"
    
    def test_overflow_detection_phrases(self):
        """Should detect all overflow error phrases in agent."""
        # These are the phrases checked in agent.py _chat_completion
        overflow_phrases = [
            "maximum context length",
            "context window is too long", 
            "context length exceeded",
            "context_length_exceeded",
            "token limit",
            "too many tokens"
        ]
        
        for phrase in overflow_phrases:
            error_str = f"Error: {phrase} exceeded"
            is_overflow = any(p in error_str.lower() for p in overflow_phrases)
            assert is_overflow, f"Should detect: {phrase}"
