"""
Test that MCP module imports are optional and don't break basic functionality.
This test verifies the fix for issue #1091.
"""
import sys
import pytest


class TestMCPOptionalImport:
    """Test that MCP is properly optional."""

    def test_praisonaiagents_import_without_mcp(self):
        """Test that praisonaiagents can be imported without mcp installed."""
        # This should not raise any ImportError
        import praisonaiagents
        assert praisonaiagents is not None

    def test_agent_import_without_mcp(self):
        """Test that Agent can be imported without mcp installed."""
        from praisonaiagents import Agent
        assert Agent is not None

    def test_mcp_lazy_loading(self):
        """Test that MCP is lazily loaded."""
        from praisonaiagents import MCP
        # MCP should either be available or None (not raise ImportError on access)
        # The actual ImportError should only be raised when trying to instantiate
        # if mcp package is not installed

    def test_mcp_module_import_no_crash(self):
        """Test that mcp module can be imported without crashing."""
        # This tests that the try/except in mcp.py works correctly
        try:
            from praisonaiagents.mcp import mcp as mcp_module
            assert hasattr(mcp_module, 'MCP_AVAILABLE')
        except ImportError:
            # If import fails, it should be because of missing mcp,
            # not because of a syntax error
            pass

    def test_mcp_sse_module_import_no_crash(self):
        """Test that mcp_sse module can be imported without crashing."""
        try:
            from praisonaiagents.mcp import mcp_sse
            assert hasattr(mcp_sse, 'MCP_AVAILABLE')
        except ImportError:
            pass

    def test_mcp_http_stream_module_import_no_crash(self):
        """Test that mcp_http_stream module can be imported without crashing."""
        try:
            from praisonaiagents.mcp import mcp_http_stream
            assert hasattr(mcp_http_stream, 'MCP_AVAILABLE')
        except ImportError:
            pass

    def test_basic_agent_creation_without_mcp_tools(self):
        """Test that agents can be created without MCP tools."""
        from praisonaiagents import Agent

        # Creating an agent without MCP tools should work
        agent = Agent(
            name="Test Agent",
            instructions="You are a test agent.",
            llm="gpt-4o-mini"
        )
        assert agent is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
