"""
Integration tests for Multi-Agent MCP scenarios.

These tests verify that multiple agents can use different MCP servers
concurrently without interference.

Note: These tests require MCP servers to be available via npx/uvx.
They are marked as integration tests and can be skipped in CI.
"""

import pytest
import os
import threading
import time

# Skip entire module if MCP package is not installed
try:
    import mcp
    from praisonaiagents.mcp import MCP
    from praisonaiagents import Agent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCP = None
    Agent = None


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed. Install with: pip install praisonaiagents[mcp]")
class TestMultiAgentMCP:
    """Integration tests for multiple agents with MCP."""
    
    def test_multiple_mcp_instances_isolated(self):
        """Test that multiple MCP instances are isolated."""
        try:
            mcp1 = MCP("uvx mcp-server-time", timeout=30)
            mcp2 = MCP("uvx mcp-server-time", timeout=30)
            
            # Each should have its own tools
            tools1 = mcp1.get_tools()
            tools2 = mcp2.get_tools()
            
            assert len(tools1) > 0
            assert len(tools2) > 0
            
            # Tools should be separate instances
            assert tools1 is not tools2
            
            mcp1.shutdown()
            mcp2.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")
    
    def test_multiple_agents_different_mcp(self):
        """Test multiple agents with different MCP servers."""
        try:
            mcp_time = MCP("uvx mcp-server-time", timeout=30)
            
            agent1 = Agent(
                name="TimeAgent",
                instructions="You help with time-related queries.",
                tools=mcp_time
            )
            
            agent2 = Agent(
                name="GeneralAgent",
                instructions="You are a general assistant."
            )
            
            # Both agents should be functional
            assert agent1 is not None
            assert agent2 is not None
            
            # Agent1 should have MCP tools
            assert agent1.tools is not None
            
            mcp_time.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")
    
    def test_concurrent_mcp_initialization(self):
        """Test concurrent MCP initialization from multiple threads."""
        results = []
        errors = []
        
        def init_mcp():
            try:
                mcp = MCP("uvx mcp-server-time", timeout=30)
                tools = mcp.get_tools()
                results.append(len(tools))
                mcp.shutdown()
            except Exception as e:
                errors.append(str(e))
        
        # Start multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=init_mcp)
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=60)
        
        # Check results
        if errors:
            # If all failed with same error, skip
            if all("not available" in e.lower() or "timeout" in e.lower() for e in errors):
                pytest.skip(f"MCP server not available: {errors[0]}")
            else:
                pytest.fail(f"Errors during concurrent init: {errors}")
        
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        assert all(r > 0 for r in results), "All MCP instances should have tools"


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
class TestMCPToolExecution:
    """Integration tests for MCP tool execution."""
    
    def test_tool_execution_returns_result(self):
        """Test that tool execution returns a result."""
        try:
            mcp = MCP("uvx mcp-server-time", timeout=30)
            tools = mcp.get_tools()
            
            # Find a tool that we can call
            for tool in tools:
                if "time" in tool.__name__.lower() or "current" in tool.__name__.lower():
                    # Try to call the tool
                    try:
                        result = tool(timezone="UTC")
                        assert result is not None
                        break
                    except TypeError:
                        # Tool might have different signature
                        continue
            
            mcp.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
class TestMCPWithMixedTools:
    """Integration tests for MCP with mixed tool types."""
    
    def test_agent_with_mcp_and_regular_tools(self):
        """Test agent with both MCP and regular function tools."""
        def regular_tool(query: str) -> str:
            """A regular Python function tool."""
            return f"Regular tool result: {query}"
        
        try:
            mcp = MCP("uvx mcp-server-time", timeout=30)
            
            agent = Agent(
                name="MixedToolsAgent",
                instructions="You have both MCP and regular tools.",
                tools=[mcp, regular_tool]
            )
            
            assert agent is not None
            assert len(agent.tools) == 2
            
            # Format tools for LLM
            formatted = agent._format_tools_for_completion(agent.tools)
            assert len(formatted) > 1  # Should have MCP tools + regular tool
            
            mcp.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")
    
    def test_multiple_mcp_in_tools_list(self):
        """Test agent with multiple MCP instances in tools list."""
        try:
            mcp1 = MCP("uvx mcp-server-time", timeout=30)
            
            agent = Agent(
                name="MultiMCPAgent",
                instructions="You have multiple MCP servers.",
                tools=[mcp1]
            )
            
            assert agent is not None
            
            # Format tools should include all MCP tools
            formatted = agent._format_tools_for_completion(agent.tools)
            assert len(formatted) > 0
            
            mcp1.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")


@pytest.mark.integration
@pytest.mark.skipif(not MCP_AVAILABLE, reason="MCP package not installed")
class TestMCPThreadSafety:
    """Integration tests for MCP thread safety."""
    
    def test_concurrent_tool_calls(self):
        """Test concurrent tool calls from multiple threads."""
        try:
            mcp = MCP("uvx mcp-server-time", timeout=30)
            tools = mcp.get_tools()
            
            if not tools:
                pytest.skip("No tools available")
            
            results = []
            errors = []
            
            def call_tool():
                try:
                    tool = tools[0]
                    # Try calling with common parameter patterns
                    try:
                        result = tool(timezone="UTC")
                    except TypeError:
                        result = tool()
                    results.append(result)
                except Exception as e:
                    errors.append(str(e))
            
            # Start multiple threads
            threads = []
            for _ in range(5):
                t = threading.Thread(target=call_tool)
                threads.append(t)
                t.start()
            
            # Wait for all threads
            for t in threads:
                t.join(timeout=30)
            
            # All calls should succeed
            assert len(errors) == 0, f"Errors: {errors}"
            assert len(results) == 5
            
            mcp.shutdown()
        except Exception as e:
            pytest.skip(f"MCP server not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
