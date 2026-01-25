"""
Tests for Simplified hook API (add_hook, remove_hook, has_hook, run_hook).

These tests verify the beginner-friendly API that accepts both string and HookEvent enum.
"""

import pytest
from unittest.mock import MagicMock

from praisonaiagents.hooks.types import HookEvent, HookResult, HookInput
from praisonaiagents.hooks.registry import (
    add_hook, remove_hook, has_hook,
    get_default_registry, HookRegistry
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the default registry before each test."""
    registry = get_default_registry()
    registry.clear()
    yield
    registry.clear()


# =============================================================================
# add_hook Tests
# =============================================================================

class TestAddHook:
    """Tests for add_hook() Simplified API."""
    
    def test_add_hook_with_string_event(self):
        """Test add_hook accepts string event name."""
        def my_hook(data):
            return HookResult.allow()
        
        hook_id = add_hook('before_tool', my_hook)
        
        assert hook_id is not None
        assert has_hook('before_tool')
    
    def test_add_hook_with_enum_event(self):
        """Test add_hook accepts HookEvent enum."""
        def my_hook(data):
            return HookResult.allow()
        
        hook_id = add_hook(HookEvent.BEFORE_TOOL, my_hook)
        
        assert hook_id is not None
        assert has_hook(HookEvent.BEFORE_TOOL)
    
    def test_add_hook_string_matches_enum(self):
        """Test that string and enum register to same event."""
        def hook1(data):
            return HookResult.allow()
        
        def hook2(data):
            return HookResult.allow()
        
        # Register with string
        add_hook('before_tool', hook1)
        
        # Register with enum
        add_hook(HookEvent.BEFORE_TOOL, hook2)
        
        # Both should be registered under same event
        registry = get_default_registry()
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL)
        assert len(hooks) == 2
    
    def test_add_hook_invalid_string_raises(self):
        """Test add_hook raises for invalid string event."""
        def my_hook(data):
            return HookResult.allow()
        
        with pytest.raises(ValueError, match="Unknown hook event"):
            add_hook('invalid_event', my_hook)
    
    def test_add_hook_decorator_style(self):
        """Test add_hook can be used as decorator."""
        @add_hook('after_tool')
        def my_hook(data):
            return HookResult.allow()
        
        assert has_hook('after_tool')
    
    def test_add_hook_all_valid_string_events(self):
        """Test all HookEvent values work as strings."""
        valid_events = [
            'before_tool', 'after_tool',
            'before_agent', 'after_agent',
            'session_start', 'session_end',
            'before_llm', 'after_llm',
            'on_error', 'on_retry'
        ]
        
        for event in valid_events:
            hook_id = add_hook(event, lambda d: HookResult.allow())
            assert hook_id is not None, f"Failed for event: {event}"
    
    def test_add_hook_with_matcher(self):
        """Test add_hook accepts matcher parameter."""
        def my_hook(data):
            return HookResult.allow()
        
        hook_id = add_hook('before_tool', my_hook, matcher='write_.*')
        
        registry = get_default_registry()
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL, 'write_file')
        assert len(hooks) == 1
        
        hooks = registry.get_hooks(HookEvent.BEFORE_TOOL, 'read_file')
        assert len(hooks) == 0


# =============================================================================
# remove_hook Tests
# =============================================================================

class TestRemoveHook:
    """Tests for remove_hook() Simplified API."""
    
    def test_remove_hook_by_id(self):
        """Test removing hook by ID."""
        def my_hook(data):
            return HookResult.allow()
        
        hook_id = add_hook('before_tool', my_hook)
        assert has_hook('before_tool')
        
        result = remove_hook(hook_id)
        
        assert result is True
        assert not has_hook('before_tool')
    
    def test_remove_nonexistent_hook(self):
        """Test removing non-existent hook returns False."""
        result = remove_hook('nonexistent-id')
        assert result is False


# =============================================================================
# has_hook Tests
# =============================================================================

class TestHasHook:
    """Tests for has_hook() Simplified API."""
    
    def test_has_hook_when_empty(self):
        """Test has_hook returns False when no hooks registered."""
        assert not has_hook('before_tool')
        assert not has_hook(HookEvent.BEFORE_TOOL)
    
    def test_has_hook_when_registered(self):
        """Test has_hook returns True when hook registered."""
        add_hook('before_tool', lambda d: HookResult.allow())
        
        assert has_hook('before_tool')
    
    def test_has_hook_with_string_and_enum_equivalent(self):
        """Test has_hook works with both string and enum for same event."""
        add_hook('before_tool', lambda d: HookResult.allow())
        
        assert has_hook('before_tool')
        assert has_hook(HookEvent.BEFORE_TOOL)
    
    def test_has_hook_invalid_string_raises(self):
        """Test has_hook raises for invalid string event."""
        with pytest.raises(ValueError, match="Unknown hook event"):
            has_hook('invalid_event')


# =============================================================================
# String/Enum Equivalence Tests
# =============================================================================

class TestStringEnumEquivalence:
    """Tests confirming string and HookEvent enum are equivalent."""
    
    def test_hook_event_equals_string(self):
        """Test HookEvent enum equals its string value."""
        assert HookEvent.BEFORE_TOOL == "before_tool"
        assert HookEvent.AFTER_TOOL == "after_tool"
        assert HookEvent.BEFORE_LLM == "before_llm"
        assert HookEvent.AFTER_LLM == "after_llm"
    
    def test_hook_event_string_conversion(self):
        """Test HookEvent can be constructed from string."""
        event = HookEvent("before_tool")
        assert event == HookEvent.BEFORE_TOOL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
