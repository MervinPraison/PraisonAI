"""
Tests for tool availability gating functionality.

Tests the ToolAvailabilityProtocol and availability filtering in the registry.
"""

import os
import pytest
from unittest.mock import Mock, patch

from praisonaiagents.tools import tool, list_available_tools, get_registry
from praisonaiagents.tools.protocols import ToolAvailabilityProtocol
from praisonaiagents.tools.base import BaseTool


def test_tool_availability_protocol():
    """Test that the ToolAvailabilityProtocol works correctly."""
    
    class MockTool:
        def check_availability(self) -> tuple[bool, str]:
            return True, ""
    
    # Test protocol compliance
    mock_tool = MockTool()
    assert isinstance(mock_tool, ToolAvailabilityProtocol)


def test_tool_decorator_with_availability():
    """Test that the @tool decorator accepts availability parameter."""
    
    @tool(availability=lambda: (True, ""))
    def available_tool(x: str) -> str:
        return f"result: {x}"
    
    # Test that the availability check works
    assert hasattr(available_tool, 'check_availability')
    is_available, reason = available_tool.check_availability()
    assert is_available is True
    assert reason == ""


def test_tool_decorator_with_unavailable():
    """Test tool decorator with unavailable tool."""
    
    @tool(availability=lambda: (False, "Missing API key"))
    def unavailable_tool(x: str) -> str:
        return f"result: {x}"
    
    # Test that the availability check works
    is_available, reason = unavailable_tool.check_availability()
    assert is_available is False
    assert reason == "Missing API key"


def test_tool_decorator_no_availability():
    """Test tool decorator without availability - should default to available."""
    
    @tool
    def default_tool(x: str) -> str:
        return f"result: {x}"
    
    # Should default to available
    is_available, reason = default_tool.check_availability()
    assert is_available is True
    assert reason == ""


def test_tool_availability_with_env_var():
    """Test tool availability based on environment variable."""
    
    # Test with missing env var
    @tool(availability=lambda: (bool(os.getenv("TEST_API_KEY")), "TEST_API_KEY missing"))
    def env_tool(x: str) -> str:
        return f"result: {x}"
    
    # Should be unavailable without env var
    is_available, reason = env_tool.check_availability()
    assert is_available is False
    assert reason == "TEST_API_KEY missing"
    
    # Test with env var set
    with patch.dict(os.environ, {'TEST_API_KEY': 'test-key'}):
        is_available, reason = env_tool.check_availability()
        assert is_available is True
        assert reason == "TEST_API_KEY missing"  # Reason is from lambda, not necessarily empty


def test_registry_list_available_tools():
    """Test that registry filters unavailable tools."""
    
    registry = get_registry()
    
    # Clear registry for clean test
    registry.clear()
    
    # Create available and unavailable tools
    @tool(availability=lambda: (True, ""))
    def available_tool(x: str) -> str:
        return "available"
    
    @tool(availability=lambda: (False, "Not available"))  
    def unavailable_tool(x: str) -> str:
        return "unavailable"
    
    # Register tools
    registry.register(available_tool)
    registry.register(unavailable_tool)
    
    # Test that all tools are returned by list_tools
    all_tools = registry.list_tools()
    assert "available_tool" in all_tools
    assert "unavailable_tool" in all_tools
    
    # Test that only available tools are returned by list_available_tools
    available_tools = registry.list_available_tools()
    available_names = [t.name for t in available_tools if hasattr(t, 'name')]
    
    assert len([t for t in available_tools if hasattr(t, 'name') and t.name == "available_tool"]) == 1
    assert len([t for t in available_tools if hasattr(t, 'name') and t.name == "unavailable_tool"]) == 0


def test_availability_check_exception_handling():
    """Test that exceptions in availability checks are handled gracefully."""
    
    def failing_check():
        raise ValueError("Availability check failed")
    
    @tool(availability=failing_check)
    def failing_tool(x: str) -> str:
        return "result"
    
    # Should handle exception and return False
    is_available, reason = failing_tool.check_availability()
    assert is_available is False
    assert "Availability check failed: Availability check failed" in reason


def test_base_tool_availability_default():
    """Test that BaseTool without availability check is always available."""
    
    class SimpleBaseTool(BaseTool):
        name = "simple"
        description = "Simple tool"

        def __init__(self):
            super().__init__()
            
        def run(self, **kwargs):
            return "result"
    
    tool = SimpleBaseTool()
    
    # Should not have check_availability method
    assert not hasattr(tool, 'check_availability')
    
    # Registry should treat it as available
    registry = get_registry()
    registry.clear()
    registry.register(tool)
    
    available_tools = registry.list_available_tools()
    assert len(available_tools) == 1
    assert available_tools[0] == tool


def test_list_available_tools_module_function():
    """Test the module-level list_available_tools function."""
    
    registry = get_registry()
    registry.clear()
    
    @tool(availability=lambda: (True, ""))
    def test_tool(x: str) -> str:
        return "test"
    
    registry.register(test_tool)
    
    # Test module function
    available = list_available_tools()
    assert len(available) == 1
    assert available[0].name == "test_tool"


def test_transient_probe_failure_serves_last_good():
    """A flaky probe exception within the grace window serves the last-good result."""

    registry = get_registry()
    registry.clear()

    class FlakyTool(BaseTool):
        name = "flaky_tool"
        description = "Flaky tool"

        def __init__(self):
            super().__init__()
            self.calls = 0

        def run(self, **kwargs):
            return "result"

        def check_availability(self):
            self.calls += 1
            # First call succeeds, subsequent calls raise (transient failure)
            if self.calls == 1:
                return True, ""
            raise RuntimeError("daemon momentarily busy")

    flaky = FlakyTool()
    registry.register(flaky, name="flaky_tool")

    # First probe succeeds and records last-success
    available = registry.list_available_tools(ttl_seconds=0)
    assert any(getattr(t, "name", None) == "flaky_tool" for t in available)

    # Second probe raises but is within the grace window -> last-good served
    available = registry.list_available_tools(ttl_seconds=0)
    assert any(getattr(t, "name", None) == "flaky_tool" for t in available)

    # The transient failure must NOT be cached as a durable negative
    cached = registry._availability_cache.get("flaky_tool")
    assert cached is None or cached[0] is not False


def test_sustained_probe_failure_marks_unavailable():
    """A probe exception beyond the grace window marks the tool unavailable."""

    registry = get_registry()
    registry.clear()

    class BrokenTool(BaseTool):
        name = "broken_tool"
        description = "Broken tool"

        def run(self, **kwargs):
            return "result"

        def check_availability(self):
            raise RuntimeError("network unreachable")

    broken = BrokenTool()
    registry.register(broken, name="broken_tool")

    # No prior success -> sustained failure -> unavailable and cached negative
    available = registry.list_available_tools(ttl_seconds=0)
    assert not any(getattr(t, "name", None) == "broken_tool" for t in available)
    assert registry._availability_cache.get("broken_tool", (True, 0))[0] is False


def test_transient_failure_expires_after_grace_window():
    """Once the grace window elapses, a sustained failure marks the tool unavailable."""

    registry = get_registry()
    registry.clear()

    class FlakyTool(BaseTool):
        name = "grace_tool"
        description = "Grace tool"

        def __init__(self):
            super().__init__()
            self.calls = 0

        def run(self, **kwargs):
            return "result"

        def check_availability(self):
            self.calls += 1
            if self.calls == 1:
                return True, ""
            raise RuntimeError("still broken")

    flaky = FlakyTool()
    registry.register(flaky, name="grace_tool")
    # Shrink grace window so we don't depend on wall-clock sleeps
    registry._availability_grace = 0.0

    # First probe records success
    registry.list_available_tools(ttl_seconds=0)

    # With grace window of 0, the next failing probe is treated as sustained
    available = registry.list_available_tools(ttl_seconds=0)
    assert not any(getattr(t, "name", None) == "grace_tool" for t in available)
    assert registry._availability_cache.get("grace_tool", (True, 0))[0] is False


def test_overwrite_replacement_does_not_inherit_last_good():
    """Replacing a healthy tool must not let a broken replacement ride its grace window."""

    registry = get_registry()
    registry.clear()

    class HealthyTool(BaseTool):
        name = "swap_tool"
        description = "Healthy tool"

        def run(self, **kwargs):
            return "ok"

        def check_availability(self):
            return True, ""

    class BrokenReplacement(BaseTool):
        name = "swap_tool"
        description = "Broken replacement"

        def run(self, **kwargs):
            return "boom"

        def check_availability(self):
            raise RuntimeError("never healthy")

    # Register healthy tool and record a successful probe.
    registry.register(HealthyTool(), name="swap_tool")
    available = registry.list_available_tools(ttl_seconds=0)
    assert any(getattr(t, "name", None) == "swap_tool" for t in available)
    assert "swap_tool" in registry._availability_last_success

    # Replace under the same name with a tool that always fails its probe.
    registry.register(BrokenReplacement(), name="swap_tool", overwrite=True)

    # Stale success state must be evicted so the replacement is NOT served.
    assert "swap_tool" not in registry._availability_last_success
    available = registry.list_available_tools(ttl_seconds=0)
    assert not any(getattr(t, "name", None) == "swap_tool" for t in available)
    assert registry._availability_cache.get("swap_tool", (True, 0))[0] is False


if __name__ == "__main__":
    pytest.main([__file__])
