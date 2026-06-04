#!/usr/bin/env python3
"""
Simple test script to verify toolsets functionality works correctly.
"""

import sys
import os

# Add the praisonai-agents package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_toolset_basic():
    """Test basic toolset functionality."""
    print("Testing basic toolset functionality...")
    
    try:
        # Import toolset functionality
        from praisonaiagents.toolsets import (
            register_toolset, resolve_toolset, list_toolsets, get_toolset
        )
        print("✓ Successfully imported toolset functions")
        
        # Test registering a custom toolset with unique names to avoid pollution
        import uuid
        test_toolset_name = f"test_toolset_{uuid.uuid4().hex[:8]}"
        composed_toolset_name = f"composed_test_{uuid.uuid4().hex[:8]}"
        
        try:
            register_toolset(
                test_toolset_name,
                tools=["tool1", "tool2"],
                description="Test toolset"
            )
            print("✓ Successfully registered custom toolset")
            
            # Test resolving the toolset
            tools = resolve_toolset(test_toolset_name)
            assert tools == ["tool1", "tool2"]
            print("✓ Successfully resolved toolset")
            
            # Test listing toolsets (should include prebuilt ones)
            toolset_list = list_toolsets()
            assert test_toolset_name in toolset_list
            assert "web" in toolset_list
            assert "research" in toolset_list
            print(f"✓ Found {len(toolset_list)} toolsets: {toolset_list}")
            
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
            print("✓ Successfully tested toolset composition")
        finally:
            # Cleanup to avoid registry pollution
            from praisonaiagents.toolsets import unregister_toolset
            try:
                unregister_toolset(composed_toolset_name)
                unregister_toolset(test_toolset_name)
            except Exception:
                pass
        
        print("All basic toolset tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ Basic toolset test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_integration():
    """Test that Agent class can use toolsets."""
    print("Testing Agent integration with toolsets...")
    
    try:
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.toolsets import register_toolset
        
        # Register a simple test toolset with real tool names
        register_toolset(
            "agent_test",
            tools=["internet_search", "read_file"],
            description="Test toolset for agent integration"
        )
        print("✓ Successfully registered agent test toolset")
        
        # Create agent with toolsets (without running it)
        agent = Agent(
            name="test_agent",
            role="Test agent",
            toolsets=["agent_test"]
        )
        print("✓ Successfully created Agent with toolsets")
        
        # Check that tools were resolved
        tool_names = []
        for tool in agent.tools:
            if hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            elif hasattr(tool, 'name'):
                tool_names.append(tool.name)
        
        print(f"✓ Agent has {len(agent.tools)} tools: {tool_names}")
        
        # Verify expected tools are present
        assert "internet_search" in tool_names, f"internet_search was not resolved from toolset. Available: {tool_names}"
        assert "read_file" in tool_names, f"read_file was not resolved from toolset. Available: {tool_names}"
        print("✓ Verified expected tools are present")
        
        # Test mixing tools and toolsets
        agent2 = Agent(
            name="test_agent2", 
            role="Test agent 2",
            tools=["write_file"],  # explicit tool
            toolsets=["agent_test"]  # toolset
        )
        print("✓ Successfully created Agent with both tools and toolsets")
        
        # Check tools in agent2
        tool_names2 = []
        for tool in agent2.tools:
            if hasattr(tool, '__name__'):
                tool_names2.append(tool.__name__)
            elif hasattr(tool, 'name'):
                tool_names2.append(tool.name)
        
        assert "write_file" in tool_names2, f"explicit tool write_file missing. Available: {tool_names2}"
        assert "internet_search" in tool_names2, f"toolset tool internet_search missing. Available: {tool_names2}"
        print("✓ Verified mixed tools and toolsets work correctly")
        
        print("All agent integration tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ Agent integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_prebuilt_toolsets():
    """Test that prebuilt toolsets work correctly."""
    print("Testing prebuilt toolsets...")
    
    try:
        from praisonaiagents.toolsets import resolve_toolset, list_toolsets
        
        # Test resolving prebuilt toolsets
        web_tools = resolve_toolset("web")
        print(f"✓ Web toolset has {len(web_tools)} tools: {web_tools}")
        
        research_tools = resolve_toolset("research")
        print(f"✓ Research toolset has {len(research_tools)} tools: {research_tools}")
        
        # Research should include web tools (via includes)
        for tool in web_tools:
            assert tool in research_tools, f"Web tool {tool} not found in research toolset"
        print("✓ Research toolset correctly includes web tools")
        
        # Test safe toolset
        safe_tools = resolve_toolset("safe")
        print(f"✓ Safe toolset has {len(safe_tools)} tools: {safe_tools}")
        
        print("All prebuilt toolset tests passed!\n")
        return True
        
    except Exception as e:
        print(f"✗ Prebuilt toolset test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing PraisonAI Toolsets Implementation")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(test_toolset_basic())
    results.append(test_agent_integration())
    results.append(test_prebuilt_toolsets())
    
    # Summary
    print("=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Toolsets implementation is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit(main())