"""
Tests for message sanitization functionality.

Tests surrogate removal, Unicode handling, and performance characteristics.
"""

import pytest
from praisonaiagents.llm.sanitize import sanitize_messages, strip_surrogates, sanitize_text


class TestStripSurrogates:
    
    def test_valid_unicode_unchanged(self):
        """Test that valid Unicode text is unchanged."""
        text = "Hello 🌍 World! 你好"
        assert strip_surrogates(text) == text
    
    def test_empty_string(self):
        """Test empty string handling."""
        assert strip_surrogates("") == ""
        assert strip_surrogates(None) is None
    
    def test_surrogate_removal(self):
        """Test removal of surrogate characters."""
        # High surrogate without low surrogate (invalid)
        text_with_surrogate = "Hello \uD83D World"
        cleaned = strip_surrogates(text_with_surrogate)
        assert "\uD83D" not in cleaned
        assert "Hello" in cleaned
        assert "World" in cleaned
    
    def test_multiple_surrogates(self):
        """Test handling of multiple surrogate characters."""
        text = "\uD800\uD801 Valid text \uDFFF"
        cleaned = strip_surrogates(text)
        assert "Valid text" in cleaned
        assert "\uD800" not in cleaned
        assert "\uD801" not in cleaned
        assert "\uDFFF" not in cleaned
    
    def test_ascii_only(self):
        """Test ASCII-only text is unchanged."""
        text = "Hello World 123 !@#"
        assert strip_surrogates(text) == text


class TestSanitizeMessages:
    
    def test_empty_messages(self):
        """Test empty message list."""
        assert sanitize_messages([]) is False
        assert sanitize_messages(None) is False
    
    def test_clean_messages_unchanged(self):
        """Test that clean messages are not modified."""
        messages = [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there! 🌍"},
        ]
        original = messages.copy()
        changed = sanitize_messages(messages)
        assert changed is False
        assert messages == original
    
    def test_sanitize_string_content(self):
        """Test sanitization of string content."""
        messages = [
            {"role": "user", "content": "Hello \uD83D World"},
            {"role": "assistant", "content": "Clean content"},
        ]
        changed = sanitize_messages(messages)
        assert changed is True
        assert "\uD83D" not in messages[0]["content"]
        assert "Hello" in messages[0]["content"]
        assert "World" in messages[0]["content"]
        assert messages[1]["content"] == "Clean content"  # Unchanged
    
    def test_sanitize_list_content(self):
        """Test sanitization of list content (multimodal)."""
        messages = [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "Hello \uD800 World"},
                    {"type": "image", "url": "http://example.com/img.jpg"},
                    "Direct string \uDFFF here"
                ]
            }
        ]
        changed = sanitize_messages(messages)
        assert changed is True
        
        content = messages[0]["content"]
        assert "\uD800" not in content[0]["text"]
        assert "Hello" in content[0]["text"] and "World" in content[0]["text"]
        assert content[1] == {"type": "image", "url": "http://example.com/img.jpg"}  # Unchanged
        assert "\uDFFF" not in content[2]
        assert "Direct string" in content[2] and "here" in content[2]
    
    def test_sanitize_other_fields(self):
        """Test sanitization of non-content fields."""
        messages = [
            {
                "role": "user",
                "content": "Clean content", 
                "name": "User\uD801Name",
                "custom_field": "Value with \uD900 surrogate"
            }
        ]
        changed = sanitize_messages(messages)
        assert changed is True
        assert "\uD801" not in messages[0]["name"]
        assert "UserName" in messages[0]["name"]
        assert "\uD900" not in messages[0]["custom_field"]
        assert "Value with" in messages[0]["custom_field"]
    
    def test_non_dict_messages_skipped(self):
        """Test that non-dict messages are skipped."""
        messages = [
            "not a dict",
            {"role": "user", "content": "Valid message"},
            None,
            {"role": "assistant", "content": "Another valid \uD800 message"}
        ]
        changed = sanitize_messages(messages)
        assert changed is True
        assert messages[0] == "not a dict"  # Unchanged
        assert messages[1]["content"] == "Valid message"  # Unchanged
        assert messages[2] is None  # Unchanged
        assert "\uD800" not in messages[3]["content"]  # Sanitized
    
    def test_performance_no_surrogates(self):
        """Test that clean messages have minimal overhead."""
        import time
        
        messages = [
            {"role": "user", "content": "Clean message " * 100},
            {"role": "assistant", "content": "Another clean message " * 100}
        ] * 100  # 200 messages total
        
        start = time.perf_counter()
        changed = sanitize_messages(messages)
        duration = time.perf_counter() - start
        
        assert changed is False
        assert duration < 0.1  # Should be very fast for clean messages


class TestSanitizeText:
    
    def test_single_text_sanitization(self):
        """Test sanitizing individual text strings."""
        assert sanitize_text("Clean text") == "Clean text"
        assert sanitize_text("Text with \uD800 surrogate") != "Text with \uD800 surrogate"
        assert "Text with" in sanitize_text("Text with \uD800 surrogate")
        assert sanitize_text(None) is None
        assert sanitize_text(123) == 123  # Non-string unchanged