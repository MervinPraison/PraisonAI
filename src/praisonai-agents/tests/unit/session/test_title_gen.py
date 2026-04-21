"""
Tests for session title auto-generation.

Tests title generation, fallback behavior, and timeout handling.
"""

import pytest
import asyncio
from praisonaiagents.session.title import generate_title, generate_title_async, _create_fallback_title


class TestTitleGeneration:
    
    def test_fallback_title(self):
        """Test fallback title generation."""
        # Basic message
        title = _create_fallback_title("Help me with Python", 60)
        assert "Help me with Python" == title
        
        # Long message gets truncated
        long_msg = "This is a very long message that should be truncated because it exceeds the maximum length limit"
        title = _create_fallback_title(long_msg, 30)
        assert len(title) <= 30
        assert title.endswith("...")
        
        # Empty message
        assert _create_fallback_title("", 60) == "Chat Session"
        assert _create_fallback_title("   ", 60) == "Chat Session"
        
        # Message with punctuation
        title = _create_fallback_title("Can you help me? Please!", 60)
        assert "?" not in title
        assert "!" not in title
        
        # Message with sentences
        title = _create_fallback_title("Help me code. I need assistance with debugging.", 60)
        assert "Help me code" in title
        assert "debugging" not in title  # Should stop at first sentence

    def test_generate_title_fallback_on_import_error(self):
        """Test that title generation falls back gracefully when LLM unavailable."""
        # This should fall back to the user message since LLM import might fail
        title = generate_title(
            "Debug my Python script",
            "I'll help you debug that",
            llm_model="fake-model",
            timeout=0.1  # Very short timeout
        )
        
        # Should get a reasonable fallback title
        assert isinstance(title, str)
        assert len(title) > 0
        assert "Debug" in title or "Python" in title or "Chat Session" in title

    @pytest.mark.asyncio
    async def test_generate_title_async_timeout(self):
        """Test async title generation with timeout."""
        title = await generate_title_async(
            "Help with machine learning",
            "I can help with ML topics",
            llm_model="fake-model",
            timeout=0.001  # Very short timeout to trigger fallback
        )
        
        # Should fall back to user message
        assert isinstance(title, str)
        assert len(title) > 0

    def test_title_length_limits(self):
        """Test that generated titles respect length limits."""
        long_user_msg = "I need help with a very complex machine learning problem " * 5
        long_assistant_msg = "I'll help you with that complex problem " * 5
        
        title = generate_title(
            long_user_msg,
            long_assistant_msg,
            llm_model="fake-model",
            max_length=20,
            timeout=0.1
        )
        
        assert len(title) <= 20

    def test_empty_messages(self):
        """Test behavior with empty or None messages."""
        title = generate_title("", "", timeout=0.1)
        assert title == "Chat Session"
        
        title = generate_title("Hello", "", timeout=0.1) 
        assert "Hello" in title or title == "Chat Session"

    def test_title_cleaning(self):
        """Test that titles are properly cleaned."""
        # Test with quotes and newlines in fallback
        title = _create_fallback_title('"Help me"\nwith this', 60)
        assert '"' in title  # Fallback doesn't clean quotes, only generation does
        
        # Test basic cleaning in fallback
        title = _create_fallback_title("Help me please!", 60)
        assert "!" not in title

    def test_unicode_handling(self):
        """Test title generation with Unicode content."""
        title = generate_title(
            "Hjälp mig med 编程",  # Swedish + Chinese
            "I can help with programming",
            timeout=0.1
        )
        
        assert isinstance(title, str)
        assert len(title) > 0

    def test_sync_wrapper(self):
        """Test that sync wrapper properly calls async version."""
        title = generate_title(
            "Test sync wrapper",
            "Testing response",
            timeout=0.1
        )
        
        assert isinstance(title, str)
        assert len(title) > 0
        # Should contain either generated content or fallback
        assert "Test" in title or "sync" in title or "Chat Session" in title