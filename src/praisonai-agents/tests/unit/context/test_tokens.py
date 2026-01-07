"""Tests for token estimation module."""

import pytest


class TestTokenEstimation:
    """Tests for token estimation functions."""
    
    def test_estimate_tokens_heuristic_empty(self):
        """Test empty string returns 0."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        assert estimate_tokens_heuristic("") == 0
    
    def test_estimate_tokens_heuristic_ascii(self):
        """Test ASCII text estimation."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        # ~4 chars per token for ASCII
        text = "Hello world"  # 11 chars
        tokens = estimate_tokens_heuristic(text)
        assert 2 <= tokens <= 4  # Should be ~2-3 tokens
    
    def test_estimate_tokens_heuristic_long_text(self):
        """Test longer text estimation."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        text = "a" * 400  # 400 ASCII chars
        tokens = estimate_tokens_heuristic(text)
        assert 90 <= tokens <= 110  # Should be ~100 tokens
    
    def test_estimate_tokens_heuristic_non_ascii(self):
        """Test non-ASCII text has higher token count."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        ascii_text = "hello"
        non_ascii_text = "你好世界"  # Chinese
        
        ascii_tokens = estimate_tokens_heuristic(ascii_text)
        non_ascii_tokens = estimate_tokens_heuristic(non_ascii_text)
        
        # Non-ASCII should have higher token density
        assert non_ascii_tokens > ascii_tokens
    
    def test_estimate_message_tokens_simple(self):
        """Test simple message token estimation."""
        from praisonaiagents.context.tokens import estimate_message_tokens
        
        msg = {"role": "user", "content": "Hello world"}
        tokens = estimate_message_tokens(msg)
        
        # Should include role overhead + content
        assert tokens > 0
        assert tokens < 20
    
    def test_estimate_message_tokens_empty_content(self):
        """Test message with empty content."""
        from praisonaiagents.context.tokens import estimate_message_tokens
        
        msg = {"role": "user", "content": ""}
        tokens = estimate_message_tokens(msg)
        
        # Should have role overhead
        assert tokens >= 4
    
    def test_estimate_message_tokens_multipart(self):
        """Test multipart content message."""
        from praisonaiagents.context.tokens import estimate_message_tokens
        
        msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"},
            ]
        }
        tokens = estimate_message_tokens(msg)
        assert tokens > 0
    
    def test_estimate_message_tokens_tool_call(self):
        """Test message with tool calls."""
        from praisonaiagents.context.tokens import estimate_message_tokens
        
        msg = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "NYC"}'
                    }
                }
            ]
        }
        tokens = estimate_message_tokens(msg)
        assert tokens > 10  # Should include tool call overhead
    
    def test_estimate_messages_tokens_list(self):
        """Test estimating tokens for message list."""
        from praisonaiagents.context.tokens import estimate_messages_tokens
        
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = estimate_messages_tokens(messages)
        assert tokens > 0
        assert tokens < 100
    
    def test_estimate_messages_tokens_empty(self):
        """Test empty message list."""
        from praisonaiagents.context.tokens import estimate_messages_tokens
        assert estimate_messages_tokens([]) == 0
    
    def test_estimate_tool_schema_tokens(self):
        """Test tool schema token estimation."""
        from praisonaiagents.context.tokens import estimate_tool_schema_tokens
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                }
            }
        ]
        tokens = estimate_tool_schema_tokens(tools)
        assert tokens > 0
    
    def test_estimate_tool_schema_tokens_empty(self):
        """Test empty tool list."""
        from praisonaiagents.context.tokens import estimate_tool_schema_tokens
        assert estimate_tool_schema_tokens([]) == 0
    
    def test_token_estimator_impl(self):
        """Test TokenEstimatorImpl class."""
        from praisonaiagents.context.tokens import TokenEstimatorImpl
        
        estimator = TokenEstimatorImpl(use_accurate=False)
        
        assert estimator.estimate("Hello") > 0
        assert estimator.estimate_messages([{"role": "user", "content": "Hi"}]) > 0
        assert estimator.estimate_tools([]) == 0
    
    def test_get_estimator(self):
        """Test get_estimator factory."""
        from praisonaiagents.context.tokens import get_estimator
        
        estimator = get_estimator(use_accurate=False)
        assert estimator is not None
        assert estimator.estimate("test") > 0


class TestTokenEstimationAccuracy:
    """Tests for estimation accuracy."""
    
    def test_consistency(self):
        """Test that estimation is consistent."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        
        text = "The quick brown fox jumps over the lazy dog"
        
        # Should return same value each time
        result1 = estimate_tokens_heuristic(text)
        result2 = estimate_tokens_heuristic(text)
        assert result1 == result2
    
    def test_proportional_scaling(self):
        """Test that longer text has more tokens."""
        from praisonaiagents.context.tokens import estimate_tokens_heuristic
        
        short = "Hello"
        long = "Hello " * 100
        
        short_tokens = estimate_tokens_heuristic(short)
        long_tokens = estimate_tokens_heuristic(long)
        
        assert long_tokens > short_tokens * 50
