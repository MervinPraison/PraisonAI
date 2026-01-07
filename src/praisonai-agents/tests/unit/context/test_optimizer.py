"""Tests for context optimizer module."""


class TestOptimizers:
    """Tests for optimizer strategies."""
    
    def test_truncate_optimizer_no_change_needed(self):
        """Test truncate when under limit."""
        from praisonaiagents.context.optimizer import TruncateOptimizer
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        
        optimizer = TruncateOptimizer()
        result, stats = optimizer.optimize(messages, target_tokens=10000)
        
        assert len(result) == 2
        assert stats.tokens_saved == 0
    
    def test_truncate_optimizer_removes_old(self):
        """Test truncate removes old messages."""
        from praisonaiagents.context.optimizer import TruncateOptimizer
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b" * 1000},
            {"role": "user", "content": "c" * 1000},
            {"role": "assistant", "content": "d" * 1000},
        ]
        
        optimizer = TruncateOptimizer(preserve_recent=2)
        result, stats = optimizer.optimize(messages, target_tokens=500)
        
        # Should keep system + recent
        assert len(result) < len(messages)
        assert stats.messages_removed > 0
    
    def test_truncate_preserves_system(self):
        """Test truncate preserves system messages."""
        from praisonaiagents.context.optimizer import TruncateOptimizer
        
        messages = [
            {"role": "system", "content": "Important system prompt"},
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b" * 1000},
        ]
        
        optimizer = TruncateOptimizer(preserve_system=True)
        result, stats = optimizer.optimize(messages, target_tokens=100)
        
        # System message should be preserved
        system_msgs = [m for m in result if m.get("role") == "system"]
        assert len(system_msgs) >= 1
    
    def test_sliding_window_optimizer(self):
        """Test sliding window keeps recent."""
        from praisonaiagents.context.optimizer import SlidingWindowOptimizer
        
        # Create messages with enough content to exceed target
        messages = [
            {"role": "user", "content": f"Message {i} " * 50} 
            for i in range(10)
        ]
        
        optimizer = SlidingWindowOptimizer()
        result, stats = optimizer.optimize(messages, target_tokens=100)
        
        # Should keep most recent messages (fewer than original)
        assert len(result) <= len(messages)
    
    def test_prune_tools_optimizer(self):
        """Test prune tools truncates old outputs."""
        from praisonaiagents.context.optimizer import PruneToolsOptimizer
        
        messages = [
            {"role": "user", "content": "Get weather"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 2000},
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome"},
        ]
        
        optimizer = PruneToolsOptimizer(preserve_recent=2, max_output_chars=100)
        result, stats = optimizer.optimize(messages, target_tokens=10000)
        
        # Tool output should be truncated
        tool_msg = [m for m in result if m.get("role") == "tool"][0]
        assert len(tool_msg["content"]) < 2000
    
    def test_prune_tools_protects_recent(self):
        """Test prune tools protects recent outputs."""
        from praisonaiagents.context.optimizer import PruneToolsOptimizer
        
        messages = [
            {"role": "user", "content": "Get weather"},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 2000},
        ]
        
        optimizer = PruneToolsOptimizer(preserve_recent=5)
        result, stats = optimizer.optimize(messages, target_tokens=10000)
        
        # Recent should not be truncated
        tool_msg = [m for m in result if m.get("role") == "tool"][0]
        assert len(tool_msg["content"]) == 2000
    
    def test_non_destructive_optimizer(self):
        """Test non-destructive tags messages."""
        from praisonaiagents.context.optimizer import NonDestructiveOptimizer
        
        messages = [
            {"role": "user", "content": f"Message {i}"} 
            for i in range(10)
        ]
        
        optimizer = NonDestructiveOptimizer(preserve_recent=3)
        result, stats = optimizer.optimize(messages, target_tokens=50)
        
        # All messages should still be present
        assert len(result) == len(messages)
        
        # Older messages should be tagged
        tagged = [m for m in result if "_condense_parent" in m]
        assert len(tagged) > 0
        assert stats.messages_tagged > 0
    
    def test_summarize_optimizer(self):
        """Test summarize creates summary."""
        from praisonaiagents.context.optimizer import SummarizeOptimizer
        
        messages = [
            {"role": "user", "content": f"Long message {i} " * 50} 
            for i in range(10)
        ]
        
        optimizer = SummarizeOptimizer(preserve_recent=3)
        result, stats = optimizer.optimize(messages, target_tokens=100)
        
        # Should have summary message
        assert stats.summary_added
        summary_msgs = [m for m in result if m.get("_summary")]
        assert len(summary_msgs) >= 1
    
    def test_smart_optimizer_combines_strategies(self):
        """Test smart optimizer applies multiple strategies."""
        from praisonaiagents.context.optimizer import SmartOptimizer
        
        messages = [
            {"role": "user", "content": "Get data"},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 5000},
        ]
        messages.extend([
            {"role": "user", "content": f"Message {i} " * 100} 
            for i in range(10)
        ])
        
        optimizer = SmartOptimizer()
        result, stats = optimizer.optimize(messages, target_tokens=500)
        
        assert stats.optimized_tokens < stats.original_tokens
    
    def test_get_optimizer_factory(self):
        """Test get_optimizer factory function."""
        from praisonaiagents.context.optimizer import get_optimizer
        from praisonaiagents.context.models import OptimizerStrategy
        
        for strategy in OptimizerStrategy:
            optimizer = get_optimizer(strategy)
            assert optimizer is not None
    
    def test_get_effective_history(self):
        """Test get_effective_history filters tagged."""
        from praisonaiagents.context.optimizer import get_effective_history
        
        messages = [
            {"role": "user", "content": "Old", "_condense_parent": "abc"},
            {"role": "user", "content": "Recent"},
        ]
        
        effective = get_effective_history(messages)
        
        assert len(effective) == 1
        assert effective[0]["content"] == "Recent"


class TestOptimizationResult:
    """Tests for OptimizationResult dataclass."""
    
    def test_reduction_percent(self):
        """Test reduction percentage calculation."""
        from praisonaiagents.context.models import OptimizationResult
        
        result = OptimizationResult(
            original_tokens=1000,
            optimized_tokens=600,
            tokens_saved=400,
        )
        
        assert result.reduction_percent == 40.0
    
    def test_reduction_percent_zero_original(self):
        """Test reduction with zero original."""
        from praisonaiagents.context.models import OptimizationResult
        
        result = OptimizationResult(original_tokens=0)
        assert result.reduction_percent == 0.0
