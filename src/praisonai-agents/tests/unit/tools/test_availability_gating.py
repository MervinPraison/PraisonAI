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


if __name__ == "__main__":
    pytest.main([__file__])
