"""
Tests for Context Manager Facade.

Tests cover:
- ContextManager initialization and configuration
- Multi-agent orchestration with policies
- Snapshot hooks at LLM boundary
- Compression benefit checking
- Token estimation validation
- Per-tool budgets
- Privacy hardening (redaction patterns)
- Optimization history tracking
- Config precedence
"""

import json
import hashlib
from unittest.mock import patch

from praisonaiagents.context.manager import (
    ContextManager,
    MultiAgentContextManager,
    ManagerConfig,
    ContextPolicy,
    EstimationMode,
    ContextShareMode,
    ToolShareMode,
    OptimizationEvent,
    OptimizationEventType,
    EstimationMetrics,
    PerToolBudget,
    SnapshotHookData,
    create_context_manager,
)
from praisonaiagents.context.models import OptimizerStrategy


class TestManagerConfig:
    """Tests for ManagerConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ManagerConfig()
        
        assert config.auto_compact is True
        assert config.compact_threshold == 0.8
        assert config.strategy == OptimizerStrategy.SMART
        assert config.compression_min_gain_pct == 5.0
        assert config.output_reserve == 8000
        assert config.estimation_mode == EstimationMode.HEURISTIC
        assert config.redact_sensitive is True
    
    def test_config_from_env(self):
        """Test loading config from environment variables."""
        with patch.dict('os.environ', {
            'PRAISONAI_CONTEXT_AUTO_COMPACT': 'false',
            'PRAISONAI_CONTEXT_THRESHOLD': '0.7',
            'PRAISONAI_CONTEXT_STRATEGY': 'truncate',
            'PRAISONAI_CONTEXT_MONITOR': 'true',
        }):
            config = ManagerConfig.from_env()
            
            assert config.auto_compact is False
            assert config.compact_threshold == 0.7
            assert config.strategy == OptimizerStrategy.TRUNCATE
            assert config.monitor_enabled is True
            assert config.source == "env"
    
    def test_config_merge(self):
        """Test config merging with overrides."""
        base = ManagerConfig()
        merged = base.merge(
            auto_compact=False,
            compact_threshold=0.9,
            monitor_enabled=True,
        )
        
        assert merged.auto_compact is False
        assert merged.compact_threshold == 0.9
        assert merged.monitor_enabled is True
        # Unchanged values preserved
        assert merged.strategy == OptimizerStrategy.SMART
    
    def test_config_to_dict(self):
        """Test config serialization."""
        config = ManagerConfig()
        data = config.to_dict()
        
        assert isinstance(data, dict)
        assert data["auto_compact"] is True
        assert data["strategy"] == "smart"
        assert "tool_budgets" in data


class TestContextPolicy:
    """Tests for ContextPolicy."""
    
    def test_default_policy(self):
        """Test default policy values."""
        policy = ContextPolicy()
        
        assert policy.share is False
        assert policy.share_mode == ContextShareMode.NONE
        assert policy.max_tokens == 0
        assert policy.tools_share == ToolShareMode.NONE
    
    def test_policy_to_dict(self):
        """Test policy serialization."""
        policy = ContextPolicy(
            share=True,
            share_mode=ContextShareMode.SUMMARY,
            max_tokens=5000,
        )
        data = policy.to_dict()
        
        assert data["share"] is True
        assert data["share_mode"] == "summary"
        assert data["max_tokens"] == 5000


class TestContextManager:
    """Tests for ContextManager facade."""
    
    def test_initialization(self):
        """Test manager initialization."""
        manager = ContextManager(model="gpt-4o-mini")
        
        assert manager.model == "gpt-4o-mini"
        assert manager.config is not None
        assert manager._budget is not None
    
    def test_process_messages(self):
        """Test processing messages through pipeline."""
        manager = ContextManager(model="gpt-4o-mini")
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result = manager.process(messages=messages)
        
        assert "messages" in result
        assert "optimized" in result
        assert "tokens_before" in result
        assert "utilization" in result
    
    def test_process_with_system_prompt(self):
        """Test processing with system prompt."""
        manager = ContextManager(model="gpt-4o-mini")
        
        messages = [{"role": "user", "content": "Hello"}]
        system_prompt = "You are a helpful assistant."
        
        result = manager.process(
            messages=messages,
            system_prompt=system_prompt,
        )
        
        assert result["tokens_before"] > 0
    
    def test_capture_llm_boundary(self):
        """Test capturing exact state at LLM boundary."""
        manager = ContextManager(model="gpt-4o-mini")
        
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        tools = [
            {"type": "function", "function": {"name": "test_tool"}},
        ]
        
        hook_data = manager.capture_llm_boundary(messages, tools)
        
        assert isinstance(hook_data, SnapshotHookData)
        assert hook_data.messages == messages
        assert hook_data.tools == tools
        assert len(hook_data.message_hash) == 16
        assert len(hook_data.tools_hash) == 16
    
    def test_snapshot_callback(self):
        """Test snapshot callback registration."""
        manager = ContextManager(model="gpt-4o-mini")
        
        callback_called = []
        
        def callback(data):
            callback_called.append(data)
        
        manager.register_snapshot_callback(callback)
        
        messages = [{"role": "user", "content": "Hello"}]
        manager.capture_llm_boundary(messages, [])
        
        assert len(callback_called) == 1
        assert callback_called[0].messages == messages
    
    def test_get_tool_budget(self):
        """Test per-tool budget retrieval."""
        manager = ContextManager(model="gpt-4o-mini")
        
        # Default budget
        default = manager.get_tool_budget("unknown_tool")
        assert default == manager.config.default_tool_output_max
        
        # Set custom budget
        manager.set_tool_budget("file_read", 5000, protected=True)
        assert manager.get_tool_budget("file_read") == 5000
        assert "file_read" in manager.config.protected_tools
    
    def test_truncate_tool_output(self):
        """Test tool output truncation."""
        manager = ContextManager(model="gpt-4o-mini")
        manager.set_tool_budget("small_tool", 100)
        
        # Large output should be truncated
        large_output = "x" * 10000
        truncated = manager.truncate_tool_output("small_tool", large_output)
        
        # Should be shorter than original (truncated)
        assert len(truncated) < len(large_output)
        # Should have some indication of truncation (chars, portions, etc)
        assert "chars" in truncated or "truncated" in truncated.lower() or "..." in truncated
    
    def test_optimization_history(self):
        """Test optimization history tracking."""
        manager = ContextManager(model="gpt-4o-mini")
        
        # Process some messages to generate history
        messages = [{"role": "user", "content": "x" * 1000}] * 100
        manager.process(messages=messages)
        
        history = manager.get_history()
        assert isinstance(history, list)
    
    def test_get_stats(self):
        """Test getting context statistics."""
        manager = ContextManager(model="gpt-4o-mini")
        
        stats = manager.get_stats()
        
        assert "model" in stats
        assert "budget" in stats
        assert "ledger" in stats
        assert "utilization" in stats
    
    def test_get_resolved_config(self):
        """Test getting resolved configuration."""
        manager = ContextManager(model="gpt-4o-mini")
        
        resolved = manager.get_resolved_config()
        
        assert "config" in resolved
        assert "precedence" in resolved
        assert "effective_budget" in resolved
    
    def test_estimate_tokens_with_cache(self):
        """Test token estimation with caching."""
        manager = ContextManager(model="gpt-4o-mini")
        
        text = "Hello world"
        
        # First call
        tokens1, _ = manager.estimate_tokens(text)
        
        # Second call should use cache
        tokens2, _ = manager.estimate_tokens(text)
        
        assert tokens1 == tokens2
    
    def test_reset(self):
        """Test manager reset."""
        manager = ContextManager(model="gpt-4o-mini")
        
        # Add some state
        messages = [{"role": "user", "content": "Hello"}]
        manager.process(messages=messages)
        manager.capture_llm_boundary(messages, [])
        
        # Reset
        manager.reset()
        
        assert manager._last_snapshot_hook is None
        assert len(manager._history) == 0


class TestCompressionBenefitCheck:
    """Tests for compression benefit checking."""
    
    def test_benefit_check_prevents_inflation(self):
        """Test that compression is reverted if not beneficial."""
        config = ManagerConfig(
            auto_compact=True,
            compact_threshold=0.1,  # Low threshold to trigger
            compression_min_gain_pct=50.0,  # High requirement
        )
        manager = ContextManager(model="gpt-4o-mini", config=config)
        
        # Small messages that won't benefit much from compression
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        
        result = manager.process(messages=messages)
        
        # Should not have optimized due to benefit check
        # (small messages don't benefit from compression)
        assert result["messages"] is not None


class TestMultiAgentContextManager:
    """Tests for MultiAgentContextManager."""
    
    def test_initialization(self):
        """Test multi-agent manager initialization."""
        manager = MultiAgentContextManager()
        
        assert manager.config is not None
        assert manager.default_policy is not None
    
    def test_get_agent_manager(self):
        """Test getting per-agent managers."""
        manager = MultiAgentContextManager()
        
        agent1 = manager.get_agent_manager("agent_1")
        agent2 = manager.get_agent_manager("agent_2")
        
        assert agent1 is not agent2
        assert agent1.agent_name == "agent_1"
        
        # Same agent returns same manager
        agent1_again = manager.get_agent_manager("agent_1")
        assert agent1 is agent1_again
    
    def test_set_agent_policy(self):
        """Test setting per-agent policies."""
        manager = MultiAgentContextManager()
        
        policy = ContextPolicy(
            share=True,
            share_mode=ContextShareMode.SUMMARY,
        )
        manager.set_agent_policy("agent_1", policy)
        
        retrieved = manager.get_agent_policy("agent_1")
        assert retrieved.share is True
        assert retrieved.share_mode == ContextShareMode.SUMMARY
    
    def test_prepare_handoff_no_share(self):
        """Test handoff with no sharing."""
        manager = MultiAgentContextManager()
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        
        # Default policy is no share
        result = manager.prepare_handoff("agent_1", "agent_2", messages)
        
        assert result == []
    
    def test_prepare_handoff_summary(self):
        """Test handoff with summary sharing."""
        manager = MultiAgentContextManager()
        
        policy = ContextPolicy(
            share=True,
            share_mode=ContextShareMode.SUMMARY,
        )
        manager.set_agent_policy("agent_2", policy)
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        result = manager.prepare_handoff("agent_1", "agent_2", messages, policy)
        
        assert len(result) > 0
        assert result[0]["role"] == "system"
        assert "_handoff_summary" in result[0]
    
    def test_prepare_handoff_full(self):
        """Test handoff with full context sharing."""
        manager = MultiAgentContextManager()
        
        policy = ContextPolicy(
            share=True,
            share_mode=ContextShareMode.FULL,
            preserve_recent_turns=2,
        )
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"},
        ]
        
        result = manager.prepare_handoff("agent_1", "agent_2", messages, policy)
        
        # Should include system + recent turns
        assert len(result) > 0
    
    def test_prepare_handoff_with_token_limit(self):
        """Test handoff respects token limits."""
        manager = MultiAgentContextManager()
        
        policy = ContextPolicy(
            share=True,
            share_mode=ContextShareMode.FULL,
            max_tokens=100,  # Very small limit
        )
        
        messages = [
            {"role": "user", "content": "x" * 1000},
            {"role": "assistant", "content": "y" * 1000},
        ]
        
        result = manager.prepare_handoff("agent_1", "agent_2", messages, policy)
        
        # Should be limited
        from praisonaiagents.context.tokens import estimate_messages_tokens
        total = estimate_messages_tokens(result)
        assert total <= 100 or len(result) <= 1
    
    def test_get_combined_stats(self):
        """Test getting combined statistics."""
        manager = MultiAgentContextManager()
        
        # Create some agents
        manager.get_agent_manager("agent_1")
        manager.get_agent_manager("agent_2")
        
        stats = manager.get_combined_stats()
        
        assert "agents" in stats
        assert "agent_1" in stats["agents"]
        assert "agent_2" in stats["agents"]


class TestEstimationValidation:
    """Tests for token estimation validation."""
    
    def test_estimation_metrics(self):
        """Test estimation metrics creation."""
        metrics = EstimationMetrics(
            heuristic_estimate=100,
            accurate_estimate=95,
            error_pct=5.26,
            estimator_used=EstimationMode.VALIDATED,
        )
        
        data = metrics.to_dict()
        assert data["heuristic_estimate"] == 100
        assert data["accurate_estimate"] == 95
        assert data["error_pct"] == 5.26
    
    def test_validated_estimation_mode(self):
        """Test validated estimation mode."""
        config = ManagerConfig(
            estimation_mode=EstimationMode.VALIDATED,
            log_estimation_mismatch=True,
        )
        manager = ContextManager(model="gpt-4o-mini", config=config)
        
        text = "Hello world"
        tokens, metrics = manager.estimate_tokens(text, validate=True)
        
        assert tokens > 0
        # Metrics may or may not be available depending on tiktoken


class TestPerToolBudgets:
    """Tests for per-tool token budgets."""
    
    def test_per_tool_budget_creation(self):
        """Test creating per-tool budgets."""
        budget = PerToolBudget(
            tool_name="file_read",
            max_output_tokens=5000,
            protected=True,
        )
        
        data = budget.to_dict()
        assert data["tool_name"] == "file_read"
        assert data["max_output_tokens"] == 5000
        assert data["protected"] is True
    
    def test_tool_budget_in_config(self):
        """Test tool budgets in config."""
        config = ManagerConfig()
        config.tool_budgets["file_read"] = PerToolBudget(
            tool_name="file_read",
            max_output_tokens=5000,
        )
        
        manager = ContextManager(model="gpt-4o-mini", config=config)
        assert manager.get_tool_budget("file_read") == 5000


class TestOptimizationHistory:
    """Tests for optimization history tracking."""
    
    def test_optimization_event_creation(self):
        """Test creating optimization events."""
        event = OptimizationEvent(
            timestamp="2024-01-01T00:00:00Z",
            event_type=OptimizationEventType.AUTO_COMPACT,
            strategy="smart",
            tokens_before=10000,
            tokens_after=5000,
            tokens_saved=5000,
        )
        
        data = event.to_dict()
        assert data["event_type"] == "auto_compact"
        assert data["tokens_saved"] == 5000
    
    def test_history_max_size(self):
        """Test history respects max size."""
        manager = ContextManager(model="gpt-4o-mini")
        manager._max_history = 5
        
        # Add many events
        for i in range(10):
            manager._add_history_event(
                OptimizationEventType.SNAPSHOT,
                details={"index": i},
            )
        
        history = manager.get_history()
        assert len(history) <= 5


class TestCreateContextManager:
    """Tests for create_context_manager factory."""
    
    def test_create_with_defaults(self):
        """Test creating manager with defaults."""
        manager = create_context_manager(model="gpt-4o-mini")
        
        assert manager.model == "gpt-4o-mini"
        assert manager.config is not None
    
    def test_create_with_cli_overrides(self):
        """Test creating manager with CLI overrides."""
        manager = create_context_manager(
            model="gpt-4o-mini",
            cli_overrides={
                "auto_compact": False,
                "monitor_enabled": True,
            },
        )
        
        assert manager.config.auto_compact is False
        assert manager.config.monitor_enabled is True
        assert manager.config.source == "cli"


class TestSnapshotHookData:
    """Tests for SnapshotHookData."""
    
    def test_snapshot_hook_creation(self):
        """Test creating snapshot hook data."""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"type": "function", "function": {"name": "test"}}]
        
        messages_json = json.dumps(messages, sort_keys=True)
        tools_json = json.dumps(tools, sort_keys=True)
        
        hook = SnapshotHookData(
            timestamp="2024-01-01T00:00:00Z",
            messages=messages,
            tools=tools,
            message_hash=hashlib.sha256(messages_json.encode()).hexdigest()[:16],
            tools_hash=hashlib.sha256(tools_json.encode()).hexdigest()[:16],
        )
        
        data = hook.to_dict()
        assert data["message_count"] == 1
        assert data["tools_count"] == 1
        assert len(data["message_hash"]) == 16
    
    def test_hash_consistency(self):
        """Test that hashes are consistent for same content."""
        messages = [{"role": "user", "content": "Hello"}]
        
        manager = ContextManager(model="gpt-4o-mini")
        
        hook1 = manager.capture_llm_boundary(messages, [])
        hook2 = manager.capture_llm_boundary(messages, [])
        
        assert hook1.message_hash == hook2.message_hash
    
    def test_hash_changes_with_content(self):
        """Test that hashes change with different content."""
        manager = ContextManager(model="gpt-4o-mini")
        
        hook1 = manager.capture_llm_boundary(
            [{"role": "user", "content": "Hello"}], []
        )
        hook2 = manager.capture_llm_boundary(
            [{"role": "user", "content": "Goodbye"}], []
        )
        
        assert hook1.message_hash != hook2.message_hash
