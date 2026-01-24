"""Tests for smart tool output summarization.

When context is over budget, tool outputs should be summarized using LLM
before falling back to truncation. This preserves key information while
reducing token count.
"""



class TestSummarizeToolOutputsOptimizer:
    """Tests for the SummarizeToolOutputsOptimizer class."""
    
    def test_tool_output_summarized_on_overflow(self):
        """Tool outputs should be summarized when over budget and LLM fn provided."""
        from praisonaiagents.context.optimizer import SummarizeToolOutputsOptimizer
        
        # Mock LLM function that returns a summary
        def mock_llm_summarize(content: str, max_tokens: int) -> str:
            return f"[Summary: {len(content)} chars summarized to {max_tokens} tokens]"
        
        optimizer = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=mock_llm_summarize,
            max_output_tokens=500,
        )
        
        # Create messages with large tool output
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Search for AI news"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "search"}}]},
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": "x" * 10000},  # Large output
            {"role": "user", "content": "Thanks"},
        ]
        
        # Target tokens that requires optimization
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Tool output should be summarized
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "[Summary:" in tool_msgs[0]["content"]
        assert tool_msgs[0].get("_summarized") is True
    
    def test_fallback_to_original_on_llm_failure(self):
        """Should keep original content if LLM summarization fails."""
        from praisonaiagents.context.optimizer import SummarizeToolOutputsOptimizer
        
        # Mock LLM function that raises an error
        def failing_llm_summarize(content: str, max_tokens: int) -> str:
            raise Exception("LLM API error")
        
        optimizer = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=failing_llm_summarize,
            max_output_tokens=500,
        )
        
        original_content = "x" * 5000
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": original_content},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Should keep original content (fallback)
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == original_content
        assert tool_msgs[0].get("_summarized") is None
    
    def test_no_summarization_without_llm_fn(self):
        """Should not modify messages when no LLM function provided."""
        from praisonaiagents.context.optimizer import SummarizeToolOutputsOptimizer
        
        optimizer = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=None,  # No LLM function
            max_output_tokens=500,
        )
        
        original_content = "x" * 5000
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": original_content},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Should keep original content
        assert result[0]["content"] == original_content
    
    def test_no_summarization_when_under_budget(self):
        """Should not summarize when already under target tokens."""
        from praisonaiagents.context.optimizer import SummarizeToolOutputsOptimizer
        
        call_count = [0]
        
        def mock_llm_summarize(content: str, max_tokens: int) -> str:
            call_count[0] += 1
            return "Summary"
        
        optimizer = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=mock_llm_summarize,
            max_output_tokens=500,
        )
        
        # Small messages that are under budget
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": "Short result"},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=10000)  # High target
        
        # LLM should not be called
        assert call_count[0] == 0
        assert result[0]["content"] == "Short result"
    
    def test_only_summarizes_large_tool_outputs(self):
        """Should only summarize tool outputs that exceed threshold."""
        from praisonaiagents.context.optimizer import SummarizeToolOutputsOptimizer
        
        summarized_contents = []
        
        def mock_llm_summarize(content: str, max_tokens: int) -> str:
            summarized_contents.append(content)
            return f"[Summary of {len(content)} chars]"
        
        optimizer = SummarizeToolOutputsOptimizer(
            llm_summarize_fn=mock_llm_summarize,
            max_output_tokens=500,
            min_chars_to_summarize=1000,  # Only summarize if > 1000 chars
        )
        
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "small_tool", "content": "Short"},  # < 1000
            {"role": "tool", "tool_call_id": "2", "name": "large_tool", "content": "x" * 5000},  # > 1000
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Only large tool output should be summarized
        assert len(summarized_contents) == 1
        assert len(summarized_contents[0]) == 5000


class TestSmartOptimizerWithToolSummarization:
    """Tests for SmartOptimizer with tool output summarization."""
    
    def test_smart_optimizer_summarizes_tools_before_truncating(self):
        """SmartOptimizer should try to summarize tool outputs before truncating."""
        from praisonaiagents.context.optimizer import SmartOptimizer
        
        summarize_called = [False]
        
        def mock_llm_summarize(messages_or_content, max_tokens: int) -> str:
            summarize_called[0] = True
            if isinstance(messages_or_content, str):
                return f"[Tool Summary: {len(messages_or_content)} chars]"
            return f"[Conversation Summary: {len(messages_or_content)} messages]"
        
        optimizer = SmartOptimizer(
            preserve_recent=2,
            llm_summarize_fn=mock_llm_summarize,
        )
        
        # Create messages with large tool output that needs optimization
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Search"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": "x" * 20000},
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome"},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=1000)
        
        # LLM summarization should have been called
        assert summarize_called[0] is True
    
    def test_smart_optimizer_respects_smart_tool_summarize_false(self):
        """SmartOptimizer should skip tool summarization when disabled."""
        from praisonaiagents.context.optimizer import SmartOptimizer
        
        summarize_called = [False]
        
        def mock_llm_summarize(messages_or_content, max_tokens: int) -> str:
            summarize_called[0] = True
            return "Summary"
        
        optimizer = SmartOptimizer(
            preserve_recent=2,
            llm_summarize_fn=mock_llm_summarize,
            smart_tool_summarize=False,  # Disabled
        )
        
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "search", "content": "x" * 10000},
        ]
        
        result, opt_result = optimizer.optimize(messages, target_tokens=500)
        
        # Tool summarization should be skipped (only conversation summarization may happen)
        # The tool output should be truncated, not summarized
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        if tool_msgs:
            # Should be truncated (pruned), not summarized
            assert tool_msgs[0].get("_summarized") is None


class TestContextConfigSmartToolSummarize:
    """Tests for smart_tool_summarize config option."""
    
    def test_context_config_has_smart_tool_summarize(self):
        """ContextConfig should have smart_tool_summarize field."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig(smart_tool_summarize=True)
        assert config.smart_tool_summarize is True
        
        config2 = ContextConfig(smart_tool_summarize=False)
        assert config2.smart_tool_summarize is False
    
    def test_context_config_smart_tool_summarize_default_true(self):
        """smart_tool_summarize should default to True."""
        from praisonaiagents.context.models import ContextConfig
        
        config = ContextConfig()
        assert config.smart_tool_summarize is True
    
    def test_manager_config_has_smart_tool_summarize(self):
        """ManagerConfig should have smart_tool_summarize field."""
        from praisonaiagents.context.manager import ManagerConfig
        
        config = ManagerConfig(smart_tool_summarize=True)
        assert config.smart_tool_summarize is True
    
    def test_manager_config_smart_tool_summarize_default_true(self):
        """smart_tool_summarize should default to True."""
        from praisonaiagents.context.manager import ManagerConfig
        
        config = ManagerConfig()
        assert config.smart_tool_summarize is True
    
    def test_manager_config_to_dict_includes_smart_tool_summarize(self):
        """to_dict should include smart_tool_summarize."""
        from praisonaiagents.context.manager import ManagerConfig
        
        config = ManagerConfig(smart_tool_summarize=False)
        d = config.to_dict()
        assert "smart_tool_summarize" in d
        assert d["smart_tool_summarize"] is False
