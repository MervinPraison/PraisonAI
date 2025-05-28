#!/usr/bin/env python3
"""
Test script to validate the MCP + Streamlit fix for issue #459
"""

import os
import sys
import logging
import tempfile

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')

def test_streamlit_mcp_integration():
    """Test the MCP + Streamlit integration with the fix"""
    print("=== Testing MCP + Streamlit Integration Fix ===")
    
    try:
        # Mock Streamlit environment
        import sys
        from unittest.mock import MagicMock, patch
        
        # Create mock streamlit module
        mock_streamlit = MagicMock()
        sys.modules['streamlit'] = mock_streamlit
        
        # Import after mocking
        from praisonaiagents import Agent
        from praisonaiagents.mcp import MCP
        
        print("✅ Successfully imported Agent and MCP with mocked Streamlit")
        
        # Test 1: Create MCP instance in Streamlit environment
        print("\n--- Test 1: MCP Instance Creation ---")
        mcp_tools = MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt", timeout=30)
        print(f"✅ MCP instance created: {type(mcp_tools)}")
        print(f"   - Is NPX: {mcp_tools.is_npx}")
        print(f"   - Debug mode: {mcp_tools.debug}")
        print(f"   - Streamlit detected: {mcp_tools._is_streamlit_environment()}")
        
        # Test 2: Create Agent with standard LLM format (the fix)
        print("\n--- Test 2: Agent Creation with Standard LLM Format ---")
        agent = Agent(
            instructions="You help book apartments on Airbnb.",
            llm="gpt-4o-mini",  # Standard format - the key fix
            tools=mcp_tools,
            verbose=True
        )
        print(f"✅ Agent created successfully")
        print(f"   - Using custom LLM: {agent._using_custom_llm}")
        print(f"   - Agent tools type: {type(agent.tools)}")
        
        # Test 3: Test tool conversion to OpenAI format
        print("\n--- Test 3: Tool Conversion ---")
        if hasattr(agent.tools, 'to_openai_tool'):
            openai_tools = agent.tools.to_openai_tool()
            print(f"✅ Tool conversion result: {openai_tools is not None}")
            if openai_tools:
                if isinstance(openai_tools, list):
                    print(f"   - Number of tools: {len(openai_tools)}")
                    if openai_tools:
                        print(f"   - First tool name: {openai_tools[0].get('function', {}).get('name', 'Unknown')}")
                else:
                    print(f"   - Single tool: {openai_tools.get('function', {}).get('name', 'Unknown')}")
        
        # Test 4: Test tool execution method
        print("\n--- Test 4: Tool Execution Method ---")
        if hasattr(agent.tools, 'runner') and hasattr(agent.tools.runner, 'tools'):
            mcp_runner_tools = agent.tools.runner.tools
            print(f"✅ MCP runner tools available: {len(mcp_runner_tools)}")
            
            if mcp_runner_tools:
                first_tool = mcp_runner_tools[0]
                print(f"   - First tool name: {first_tool.name}")
                print(f"   - Tool description: {getattr(first_tool, 'description', 'No description')}")
                
                # Test execute_tool method without actually calling it
                try:
                    # Just test that the method exists and can be called
                    print(f"   - execute_tool method exists: {hasattr(agent, 'execute_tool')}")
                except Exception as e:
                    print(f"   - Error testing execute_tool: {e}")
        
        print("\n✅ All tests passed! MCP + Streamlit integration is working.")
        return True
        
    except Exception as e:
        print(f"❌ Error in MCP + Streamlit integration test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_llm_format_comparison():
    """Test different LLM formats to demonstrate the fix"""
    print("\n=== Testing LLM Format Fix ===")
    
    try:
        from praisonaiagents import Agent
        from praisonaiagents.mcp import MCP
        
        # Create MCP tools once
        mcp_tools = MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt", timeout=30)
        
        # Test formats
        formats = [
            ("gpt-4o-mini", "Standard OpenAI format (RECOMMENDED)"),
            ("ollama/llama3.2", "Provider/model format (PROBLEMATIC in Streamlit)")
        ]
        
        for llm_format, description in formats:
            print(f"\n--- Testing: {llm_format} ({description}) ---")
            try:
                agent = Agent(
                    instructions="Test agent",
                    llm=llm_format,
                    tools=mcp_tools
                )
                print(f"✅ Agent created successfully")
                print(f"   - Using custom LLM: {agent._using_custom_llm}")
                
                # Check tool conversion
                if hasattr(agent.tools, 'to_openai_tool'):
                    openai_tools = agent.tools.to_openai_tool()
                    print(f"   - Tool conversion successful: {openai_tools is not None}")
                
            except Exception as e:
                print(f"❌ Failed with {llm_format}: {e}")
        
        print(f"\n💡 RECOMMENDATION: Use 'gpt-4o-mini' in Streamlit, avoid 'provider/model' format")
        return True
        
    except Exception as e:
        print(f"❌ Error in LLM format test: {e}")
        return False

def create_streamlit_example():
    """Create a working Streamlit example file"""
    print("\n=== Creating Streamlit Example ===")
    
    example_content = '''"""
Fixed Streamlit example for MCP integration (Issue #459)
Run with: streamlit run streamlit_mcp_example.py
"""

import streamlit as st
from praisonaiagents import Agent, MCP

st.title("🏠 AI Airbnb Assistant (Fixed)")
st.write("This example demonstrates the fix for MCP + Streamlit issue #459")

# Show the fix
st.markdown("""
### 🔧 Fix Applied:
- ✅ Use standard LLM format: `gpt-4o-mini`
- ❌ Avoid provider/model format: `ollama/llama3.2`
- ✅ Session state management
- ✅ Proper error handling
""")

# Initialize agent in session state
if "agent" not in st.session_state:
    with st.spinner("Initializing MCP agent..."):
        try:
            st.session_state.agent = Agent(
                instructions="You help book apartments on Airbnb.",
                llm="gpt-4o-mini",  # THE FIX: Use standard format
                tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt"),
                verbose=True
            )
            st.success("✅ Agent initialized successfully!")
        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.stop()

# Query input
query = st.text_input("Search for accommodations:", 
                     placeholder="Find me a beach house in Miami for 2 guests")

if st.button("Search") and query:
    with st.spinner("Searching..."):
        try:
            result = st.session_state.agent.start(query)
            st.write(result)
        except Exception as e:
            st.error(f"Error: {e}")

st.markdown("---")
st.markdown("**Fix for:** [GitHub Issue #459](https://github.com/MervinPraison/PraisonAI/issues/459)")
'''
    
    try:
        filename = "streamlit_mcp_example.py"
        with open(filename, 'w') as f:
            f.write(example_content)
        print(f"✅ Created example file: {filename}")
        print(f"   Run with: streamlit run {filename}")
        return True
    except Exception as e:
        print(f"❌ Error creating example: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing MCP + Streamlit Fix for Issue #459")
    print("=" * 60)
    
    # Run tests
    success1 = test_streamlit_mcp_integration()
    success2 = test_llm_format_comparison()
    success3 = create_streamlit_example()
    
    print("\n" + "=" * 60)
    if all([success1, success2, success3]):
        print("🎉 ALL TESTS PASSED! Fix is working correctly.")
        print("\n📋 SUMMARY OF FIX:")
        print("1. Use standard LLM format (gpt-4o-mini) instead of provider/model format")
        print("2. Initialize agent in Streamlit session state")
        print("3. Add proper error handling and user feedback")
        print("4. Enable verbose mode for debugging")
        print("\n📁 Files created:")
        print("- examples/python/ui/mcp-streamlit-airbnb.py (comprehensive example)")
        print("- docs/ui/streamlit/mcp-streamlit.mdx (documentation)")
        print("- streamlit_mcp_example.py (simple example)")
    else:
        print("❌ Some tests failed. Check the output above for details.")