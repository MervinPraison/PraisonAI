"""Tests for new optimizer features: LLM summarization and per-tool limits."""

import pytest
from typing import Dict, Any, List


class TestLLMSummarizeOptimizer:
    """Tests for LLM-powered summarization."""
    
    def test_summarize_optimizer_with_llm_fn(self):
        """Should use LLM function when provided."""
        from praisonaiagents.context.optimizer import SummarizeOptimizer
        
        # Mock LLM function
        def mock_llm_summarize(messages: List[Dict], max_tokens: int) -> str:
            return f"[AI Summary of {len(messages)} messages]"
        
        optimizer = SummarizeOptimizer(
            preserve_recent=2,
            llm_summarize_fn=mock_llm_summarize,
        )
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello " * 100},
            {"role": "assistant", "content": "Hi there " * 100},
            {"role": "user", "content": "How are you? " * 100},
            {"role": "assistant", "content": "I'm good " * 100},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Should have summary message
        summary_msgs = [m for m in result if m.get("_summary")]
        assert len(summary_msgs) == 1
        assert "[AI Summary" in summary_msgs[0]["content"]
    
    def test_summarize_optimizer_fallback_without_llm(self):
        """Should fallback to truncation when no LLM function."""
        from praisonaiagents.context.optimizer import SummarizeOptimizer
        
        optimizer = SummarizeOptimizer(preserve_recent=2)
        
        # Create messages that exceed target to trigger optimization
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello " * 500},  # Large content
            {"role": "assistant", "content": "Hi there " * 500},  # Large content
            {"role": "user", "content": "Recent message"},
            {"role": "assistant", "content": "Recent response"},
        ]
        
        # Set very low target to force optimization
        result, opt_result = optimizer.optimize(messages, target_tokens=100)
        
        # Should have truncated summary
        summary_msgs = [m for m in result if m.get("_summary")]
        assert len(summary_msgs) == 1
        assert "[Previous conversation summary]" in summary_msgs[0]["content"]
    
    def test_llm_summarize_optimizer_class(self):
        """Should create LLMSummarizeOptimizer."""
        from praisonaiagents.context.optimizer import LLMSummarizeOptimizer
        
        # Without client, should fallback to truncation
        optimizer = LLMSummarizeOptimizer(preserve_recent=3)
        
        messages = [
            {"role": "user", "content": "Hello " * 100},
            {"role": "assistant", "content": "Hi " * 100},
            {"role": "user", "content": "Recent"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Latest"},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Should work without error
        assert len(result) > 0


class TestPerToolLimits:
    """Tests for per-tool configurable output limits."""
    
    def test_prune_tools_with_per_tool_limits(self):
        """Should use per-tool limits when configured."""
        from praisonaiagents.context.optimizer import PruneToolsOptimizer
        
        optimizer = PruneToolsOptimizer(
            preserve_recent=1,
            max_output_chars=1000,  # Default
            tool_limits={
                "tavily_search": 500,  # Smaller limit for search
                "code_executor": 2000,  # Larger limit for code
            }
        )
        
        messages = [
            {"role": "system", "content": "System"},
            {"role": "tool", "name": "tavily_search", "content": "x" * 800},  # Should truncate to 500
            {"role": "tool", "name": "code_executor", "content": "y" * 1500},  # Should NOT truncate (under 2000)
            {"role": "tool", "name": "other_tool", "content": "z" * 1200},  # Should truncate to 1000 (default)
            {"role": "user", "content": "Recent"},  # Preserved
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=50000)
        
        # Check tavily_search was truncated to 500
        tavily_msg = [m for m in result if m.get("name") == "tavily_search"][0]
        assert len(tavily_msg["content"]) <= 550  # 500 + truncation message
        assert tavily_msg.get("_pruned") is True
        
        # Check code_executor was NOT truncated
        code_msg = [m for m in result if m.get("name") == "code_executor"][0]
        assert len(code_msg["content"]) == 1500
        assert code_msg.get("_pruned") is None
        
        # Check other_tool was truncated to default 1000
        other_msg = [m for m in result if m.get("name") == "other_tool"][0]
        assert len(other_msg["content"]) <= 1050
        assert other_msg.get("_pruned") is True
    
    def test_smart_optimizer_with_tool_limits(self):
        """SmartOptimizer should pass tool_limits to PruneToolsOptimizer."""
        from praisonaiagents.context.optimizer import SmartOptimizer
        
        optimizer = SmartOptimizer(
            preserve_recent=2,
            tool_limits={"tavily_search": 300}
        )
        
        # Create messages that exceed target to trigger optimization
        messages = [
            {"role": "system", "content": "System"},
            {"role": "tool", "name": "tavily_search", "content": "x" * 600},
            {"role": "user", "content": "Recent 1 " * 500},  # Large to trigger optimization
            {"role": "assistant", "content": "Recent 2 " * 500},
        ]
        
        # Set low target to force optimization
        result, opt_result = optimizer.optimize(messages, target_tokens=100)
        
        # Check tavily_search was truncated (if it's in result)
        tavily_msgs = [m for m in result if m.get("name") == "tavily_search"]
        if tavily_msgs:
            assert len(tavily_msgs[0]["content"]) <= 350


class TestContextConfigToolLimits:
    """Tests for tool_limits in ContextConfig."""
    
    def test_context_config_has_tool_limits_field(self):
        """ContextConfig should have tool_limits field."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig(
            tool_limits={"tavily_search": 500, "code_executor": 2000}
        )
        
        assert config.tool_limits == {"tavily_search": 500, "code_executor": 2000}
    
    def test_context_config_tool_limits_default_empty(self):
        """tool_limits should default to empty dict."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig()
        
        assert config.tool_limits == {}
    
    def test_context_config_to_dict_includes_tool_limits(self):
        """to_dict should include tool_limits."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig(
            tool_limits={"search": 1000}
        )
        
        d = config.to_dict()
        assert "tool_limits" in d
        assert d["tool_limits"] == {"search": 1000}


class TestSmartOptimizerWithLLMSummarize:
    """Tests for SmartOptimizer with LLM summarization."""
    
    def test_smart_optimizer_accepts_llm_summarize_fn(self):
        """SmartOptimizer should accept llm_summarize_fn parameter."""
        from praisonaiagents.context.optimizer import SmartOptimizer
        
        def mock_summarize(messages, max_tokens):
            return "Summary"
        
        optimizer = SmartOptimizer(
            preserve_recent=3,
            llm_summarize_fn=mock_summarize,
        )
        
        # Should not raise
        assert optimizer._summarize.llm_summarize_fn is not None
