"""
Tests for session title auto-generation.

Tests title generation, fallback behavior, and timeout handling.
"""

import pytest
import asyncio
from praisonaiagents.session.title import (
    generate_title,
    generate_title_async,
    _create_fallback_title,
    _resolve_small_model,
    _DEFAULT_SMALL_MODEL,
)


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


class TestSmallModelResolution:
    """Tests for auxiliary/small model resolution in title generation."""

    def setup_method(self):
        from praisonaiagents.config.loader import clear_config_cache
        clear_config_cache()

    def teardown_method(self):
        from praisonaiagents.config.loader import clear_config_cache
        clear_config_cache()

    def test_explicit_llm_model_wins(self):
        """An explicit llm_model always takes precedence."""
        assert _resolve_small_model("explicit-model", "primary-model") == "explicit-model"

    def test_falls_back_to_primary_model(self):
        """With no config small_model, resolve to the primary model."""
        assert _resolve_small_model(None, "primary-model") == "primary-model"

    def test_falls_back_to_default_when_nothing_set(self):
        """With nothing configured, preserve the historical default."""
        assert _resolve_small_model(None, None) == _DEFAULT_SMALL_MODEL

    def test_config_small_model_used(self, monkeypatch):
        """A configured defaults.small_model is used over the primary model."""
        from praisonaiagents.config import loader

        monkeypatch.setattr(
            loader, "get_small_model",
            lambda primary_model=None, fallback=None: "config-small-model",
        )
        assert _resolve_small_model(None, "primary-model") == "config-small-model"

    def test_get_small_model_resolution_order(self):
        """get_small_model resolves small_model -> primary -> config model -> fallback."""
        from praisonaiagents.config.loader import (
            get_small_model,
            get_config,
            DefaultsConfig,
        )

        config = get_config()
        original = config.defaults
        try:
            # Unset small_model + primary given -> primary
            config.defaults = DefaultsConfig(model=None, small_model=None)
            assert get_small_model(primary_model="p", fallback="fb") == "p"
            # Unset small_model, no primary, config model set -> config model
            config.defaults = DefaultsConfig(model="cfg-model", small_model=None)
            assert get_small_model(primary_model=None, fallback="fb") == "cfg-model"
            # small_model set -> small_model wins over everything
            config.defaults = DefaultsConfig(model="cfg-model", small_model="small")
            assert get_small_model(primary_model="p", fallback="fb") == "small"
            # Nothing set -> fallback
            config.defaults = DefaultsConfig(model=None, small_model=None)
            assert get_small_model(primary_model=None, fallback="fb") == "fb"
        finally:
            config.defaults = original

    def test_agent_namespace_small_model_honored(self, monkeypatch):
        """`agent.small_model` (CLI/schema namespace) is honored by the resolver.

        The CLI resolver and JSON schema place model settings under a top-level
        `agent` section, while the typed loader uses `defaults`. Both read the
        same config file, so a schema-guided `agent.small_model` must not be
        silently ignored.
        """
        from praisonaiagents.config import loader
        from praisonaiagents.config.loader import (
            get_small_model,
            get_config,
            DefaultsConfig,
        )

        config = get_config()
        original = config.defaults
        try:
            config.defaults = DefaultsConfig(model=None, small_model=None)
            monkeypatch.setattr(
                loader, "_load_config",
                lambda: {"agent": {"small_model": "agent-small"}},
            )
            assert get_small_model(primary_model="p", fallback="fb") == "agent-small"
        finally:
            config.defaults = original

    def test_agent_namespace_model_fallback(self, monkeypatch):
        """`agent.model` is used as a fallback when no small model is set."""
        from praisonaiagents.config import loader
        from praisonaiagents.config.loader import (
            get_small_model,
            get_config,
            DefaultsConfig,
        )

        config = get_config()
        original = config.defaults
        try:
            config.defaults = DefaultsConfig(model=None, small_model=None)
            monkeypatch.setattr(
                loader, "_load_config",
                lambda: {"agent": {"model": "agent-model"}},
            )
            assert get_small_model(primary_model=None, fallback="fb") == "agent-model"
        finally:
            config.defaults = original