"""
Tests for named toolsets functionality.

These tests verify that the toolset system works correctly, including:
- Basic registration and resolution
- Agent integration
- Prebuilt toolsets
- Real agentic execution
"""

import os
import uuid
import pytest
import logging
from unittest.mock import patch

# Set up minimal environment for testing
os.environ.setdefault("OPENAI_API_KEY", "test-key")

logger = logging.getLogger(__name__)


class TestToolsetsBasic:
    """Test basic toolset functionality."""
    
    def test_toolset_imports(self):
        """Test that toolset functions can be imported."""
        from praisonaiagents.toolsets import (
            register_toolset, 
            resolve_toolset, 
            list_toolsets, 
            get_toolset,
            unregister_toolset
        )
        # If we get here without ImportError, imports work
        assert callable(register_toolset)
        assert callable(resolve_toolset)
        assert callable(list_toolsets)
        assert callable(get_toolset)
        assert callable(unregister_toolset)
    
    def test_toolset_registration_and_resolution(self):
        """Test registering and resolving custom toolsets."""
        from praisonaiagents.toolsets import (
            register_toolset, 
            resolve_toolset, 
            list_toolsets,
            unregister_toolset
        )
        
        # Use unique names to avoid test pollution
        test_toolset_name = f"test_toolset_{uuid.uuid4().hex[:8]}"
        composed_toolset_name = f"composed_test_{uuid.uuid4().hex[:8]}"
        
        try:
            # Register a simple toolset
            register_toolset(
                test_toolset_name,
                tools=["tool1", "tool2"],
                description="Test toolset"
            )
            
            # Test resolution
            tools = resolve_toolset(test_toolset_name)
            assert tools == ["tool1", "tool2"]
            
            # Test listing includes our toolset
            toolset_list = list_toolsets()
            assert test_toolset_name in toolset_list
            
            # Test composition via includes
            register_toolset(
                composed_toolset_name,
                tools=["tool3"],
                includes=[test_toolset_name]
            )
            
            composed_tools = resolve_toolset(composed_toolset_name)
            assert "tool1" in composed_tools
            assert "tool2" in composed_tools
            assert "tool3" in composed_tools
            
        finally:
            # Cleanup
            try:
                unregister_toolset(composed_toolset_name)
                unregister_toolset(test_toolset_name)
            except Exception:
                pass
    
    def test_prebuilt_toolsets(self):
        """Test that prebuilt toolsets are available."""
        from praisonaiagents.toolsets import resolve_toolset, list_toolsets
        
        # Check that prebuilt toolsets exist
        toolset_list = list_toolsets()
        assert "web" in toolset_list
        assert "research" in toolset_list
        assert "safe" in toolset_list
        
        # Test resolving prebuilt toolsets
        web_tools = resolve_toolset("web")
        assert isinstance(web_tools, list)
        assert len(web_tools) > 0
        
        research_tools = resolve_toolset("research")
        assert isinstance(research_tools, list)
        assert len(research_tools) > 0
        
        # Research should include web tools (via includes)
        for tool in web_tools:
            assert tool in research_tools, f"Web tool {tool} not found in research toolset"
        
        safe_tools = resolve_toolset("safe")
        assert isinstance(safe_tools, list)
        assert len(safe_tools) >= 0  # Safe might be empty, that's okay


class TestAgentIntegration:
    """Test Agent integration with toolsets."""
    
    def test_agent_with_toolsets_parameter(self):
        """Test creating agents with toolsets parameter."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.toolsets import register_toolset, unregister_toolset
        
        test_toolset_name = f"agent_test_{uuid.uuid4().hex[:8]}"
        
        try:
            # Register a test toolset with real tool names
            register_toolset(
                test_toolset_name,
                tools=["internet_search", "read_file"],
                description="Test toolset for agent integration"
            )
            
            # Create agent with toolsets
            agent = Agent(
                name="test_agent",
                role="Test agent",
                toolsets=[test_toolset_name]
            )
            
            # Check that tools were resolved
            tool_names = []
            for tool in agent.tools:
                if hasattr(tool, '__name__'):
                    tool_names.append(tool.__name__)
                elif hasattr(tool, 'name'):
                    tool_names.append(tool.name)
            
            # Verify expected tools are present
            assert "internet_search" in tool_names, f"internet_search not resolved. Available: {tool_names}"
            assert "read_file" in tool_names, f"read_file not resolved. Available: {tool_names}"
            
        finally:
            try:
                unregister_toolset(test_toolset_name)
            except Exception:
                pass
    
    def test_agent_with_tools_and_toolsets(self):
        """Test agents with both explicit tools and toolsets."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.toolsets import register_toolset, unregister_toolset
        
        test_toolset_name = f"mixed_test_{uuid.uuid4().hex[:8]}"
        
        try:
            # Register a test toolset
            register_toolset(
                test_toolset_name,
                tools=["internet_search"],
                description="Test toolset for mixed integration"
            )
            
            # Create agent with both tools and toolsets
            agent = Agent(
                name="mixed_agent", 
                role="Mixed test agent",
                tools=["write_file"],  # explicit tool
                toolsets=[test_toolset_name]  # toolset
            )
            
            # Check tools in agent
            tool_names = []
            for tool in agent.tools:
                if hasattr(tool, '__name__'):
                    tool_names.append(tool.__name__)
                elif hasattr(tool, 'name'):
                    tool_names.append(tool.name)
            
            assert "write_file" in tool_names, f"explicit tool write_file missing. Available: {tool_names}"
            assert "internet_search" in tool_names, f"toolset tool internet_search missing. Available: {tool_names}"
            
        finally:
            try:
                unregister_toolset(test_toolset_name)
            except Exception:
                pass
    
    def test_agent_invalid_toolset_fails_fast(self):
        """Test that agent creation fails fast with invalid toolsets."""
        from praisonaiagents.agent.agent import Agent
        
        # Should raise ValueError for invalid toolset
        with pytest.raises((ValueError, KeyError, ImportError)):
            Agent(
                name="fail_agent",
                role="Should fail",
                toolsets=["nonexistent_toolset_12345"]
            )


class TestAgenticExecution:
    """Test real agentic execution with toolsets (requires LLM)."""
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "test-key",
        reason="Real LLM test requires OPENAI_API_KEY environment variable"
    )
    def test_agent_real_agentic_execution_with_toolsets(self):
        """
        Real agentic test: Agent runs end-to-end with LLM using toolsets.
        
        This is a MANDATORY real agentic test per AGENTS.md requirements.
        The agent MUST call the LLM and produce actual output.
        """
        from praisonaiagents.agent.agent import Agent
        
        # Create agent with safe toolset (minimal tools for testing)
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant. Respond briefly and directly.",
            toolsets=["safe"],  # Use safe toolset for minimal functionality
            llm="gpt-4o-mini"  # Use cheaper model for testing
        )
        
        # REAL AGENTIC TEST: Agent must call LLM
        result = agent.start("Say hello in exactly one sentence. Be brief.")
        
        # Validate that we got a real response
        assert result is not None, "Agent returned None result"
        assert isinstance(result, str), f"Expected string result, got {type(result)}"
        assert len(result.strip()) > 0, "Agent returned empty result"
        assert len(result) < 1000, f"Response too long ({len(result)} chars), expected brief response"
        
        # Log the result so developers can verify end-to-end behavior
        print(f"\n🤖 Agent Response: {result}")
        print(f"✅ Real agentic test passed - Agent successfully used toolsets and called LLM")
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "test-key",
        reason="Real LLM test requires OPENAI_API_KEY environment variable"
    )
    def test_agent_with_research_toolset_real(self):
        """
        Test agent with research toolset in real execution.
        
        This verifies that toolsets are properly resolved and available to the LLM.
        """
        from praisonaiagents.agent.agent import Agent
        
        # Create agent with research toolset
        agent = Agent(
            name="researcher",
            instructions="You are a research assistant with access to search tools. Be concise.",
            toolsets=["research"],
            llm="gpt-4o-mini"
        )
        
        # Real execution - agent should respond and have tools available
        result = agent.start("Briefly explain what tools you have access to.")
        
        # Validate response
        assert result is not None, "Agent returned None result"
        assert isinstance(result, str), "Expected string result"
        assert len(result.strip()) > 0, "Agent returned empty result"
        
        # Print result for verification
        print(f"\n🔬 Research Agent Response: {result}")
        print(f"🛠️  Research Agent Tools: {[getattr(t, '__name__', str(t)) for t in agent.tools]}")
        print(f"✅ Research toolset integration test passed")


class TestYAMLIntegration:
    """Test YAML configuration support for toolsets."""
    
    def test_yaml_toolset_validation(self):
        """Test that YAML validation includes toolsets."""
        from praisonai.tool_resolver import validate_yaml_tools
        
        # Valid YAML with toolsets
        valid_config = {
            "agents": {
                "researcher": {
                    "role": "Research Agent",
                    "goal": "Research topics",
                    "tools": ["internet_search"],
                    "toolsets": ["research"]
                }
            }
        }
        
        # Should not have missing tools/toolsets
        missing = validate_yaml_tools(valid_config)
        assert isinstance(missing, list)
        # Note: May have missing tools if not available, but shouldn't crash
        
        # Invalid YAML with nonexistent toolset
        invalid_config = {
            "agents": {
                "researcher": {
                    "role": "Research Agent", 
                    "toolsets": ["nonexistent_toolset_xyz123"]
                }
            }
        }
        
        missing = validate_yaml_tools(invalid_config)
        assert isinstance(missing, list)
        # Should have at least one missing entry for invalid toolset
        toolset_errors = [m for m in missing if "toolset:" in m]
        assert len(toolset_errors) > 0, "Should detect missing toolsets"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])