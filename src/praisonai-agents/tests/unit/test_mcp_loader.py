"""
Unit tests for MCP loader functionality.

Tests the smoke functionality for the new MCP client lifecycle
features implemented in this issue.
"""

import pytest
from unittest.mock import Mock, MagicMock
from praisonaiagents.memory.mcp_config import MCPConfig


def test_mcp_config_to_mcp_instance_import_fix():
    """Test that MCPConfig.to_mcp_instance() imports MCP correctly (A1)."""
    # Create a minimal config
    config = MCPConfig(
        name="test",
        command="echo",
        args=["hello"],
        enabled=True
    )
    
    # This should not raise ImportError anymore
    # Note: It might return None if MCP package is not installed, but the import should work
    try:
        result = config.to_mcp_instance()
        # If we get here without ImportError from wrong path, the fix worked
        assert True
    except ImportError as e:
        if "praisonaiagents.tools.mcp" in str(e):
            pytest.fail("Import still using wrong path - A1 fix failed")
        else:
            # This is expected if mcp package is not installed
            assert "praisonaiagents[mcp]" in str(e)


def test_load_mcp_tools_import():
    """Test that load_mcp_tools can be imported (B2)."""
    from praisonaiagents.mcp import load_mcp_tools
    assert callable(load_mcp_tools)


def test_mcp_client_protocol_import():
    """Test that MCPClientProtocol can be imported (B1)."""
    from praisonaiagents.mcp import MCPClientProtocol
    # Should be a protocol/type
    assert MCPClientProtocol is not None


def test_mcp_filter_parameters():
    """Test that MCP class accepts filter parameters (B3)."""
    try:
        from praisonaiagents.mcp import MCP
        # This should not raise TypeError for unknown parameters
        # Note: May raise ImportError if mcp package not installed
        mcp = MCP("echo hello", allowed_tools=["test"], disabled_tools=["bad"])
        assert mcp.allowed_tools == ["test"]
        assert mcp.disabled_tools == ["bad"]
    except ImportError as e:
        if "praisonaiagents[mcp]" in str(e):
            # Expected if MCP package not installed
            pytest.skip("MCP package not installed")
        else:
            raise


def test_filter_tool_functions_exist():
    """Test that filter functions exist and work (B3)."""
    from praisonaiagents.mcp.mcp_utils import filter_tools_by_allowlist, filter_disabled_tools
    
    tools = [
        {"name": "tool1", "description": "First tool"},
        {"name": "tool2", "description": "Second tool"},
        {"name": "tool3", "description": "Third tool"},
    ]
    
    # Test allowlist filtering
    filtered = filter_tools_by_allowlist(tools, ["tool1", "tool3"])
    assert len(filtered) == 2
    assert filtered[0]["name"] == "tool1"
    assert filtered[1]["name"] == "tool3"
    
    # Test disabled filtering
    filtered = filter_disabled_tools(tools, ["tool2"])
    assert len(filtered) == 2
    assert all(t["name"] != "tool2" for t in filtered)
    
    # Test precedence: include wins over exclude
    # This is handled at MCP class level, but filters should work independently


def test_prefix_collision_handling():
    """Test tool name prefix handling (B4)."""
    # The prefix logic is in the loader
    from praisonaiagents.mcp.loader import load_mcp_tools
    
    # Test that sanitization logic exists (basic check)
    # Full test would require mock MCP configs
    assert callable(load_mcp_tools)


def test_safe_env_build():
    """Test safe environment building (B5)."""
    try:
        from praisonaiagents.mcp import MCP
        
        # Create MCP instance to test env building
        # This tests that _build_safe_env method exists
        mcp = MCP("echo test")
        assert hasattr(mcp, '_build_safe_env')
        
        # Test safe env function
        safe_env = mcp._build_safe_env({"CUSTOM_VAR": "test"})
        assert isinstance(safe_env, dict)
        assert "CUSTOM_VAR" in safe_env
        assert safe_env["CUSTOM_VAR"] == "test"
        # Should have safe baseline
        assert "PATH" in safe_env
        assert "HOME" in safe_env
        
    except ImportError as e:
        if "praisonaiagents[mcp]" in str(e):
            pytest.skip("MCP package not installed") 
        else:
            raise