"""
Working Streamlit example with MCP Airbnb integration
This demonstrates the fix for issue #459: MCP doesn't work in Streamlit
"""

import streamlit as st
import sys
import os

# Add the src directory to Python path if running locally
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    from praisonaiagents.mcp import MCP
except ImportError as e:
    st.error(f"Import error: {e}")
    st.error("Please ensure praisonaiagents is installed: pip install praisonaiagents")
    st.stop()

st.title("🏠 AI Airbnb Assistant with MCP")
st.write("This example demonstrates MCP integration with Streamlit (Fix for Issue #459)")

# Configuration section
with st.expander("⚙️ Configuration", expanded=False):
    st.markdown("""
    **Current Configuration:**
    - **MCP Server**: NPX Airbnb MCP Server
    - **LLM**: OpenAI GPT-4o-mini (recommended for tool calling)
    - **Tools**: Airbnb search and booking tools via MCP
    """)

# Initialize session state
if "agent" not in st.session_state:
    with st.spinner("🔄 Initializing MCP Airbnb agent..."):
        try:
            # Use OpenAI model instead of ollama to avoid provider/model issues
            # This is the key fix - avoid ollama/model format in Streamlit
            st.session_state.agent = Agent(
                instructions="""You are an expert Airbnb assistant. Help users find and book amazing accommodations.
                
When searching for properties, always include:
- Location details
- Price range
- Property features
- Availability
- Guest ratings
                
Be helpful, friendly, and provide detailed recommendations.""",
                llm="gpt-4o-mini",  # Use standard OpenAI format instead of ollama/llama3.2
                tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt"),
                verbose=True  # Enable verbose mode for debugging
            )
            st.success("✅ MCP Airbnb agent initialized successfully!")
            
            # Display available tools
            if hasattr(st.session_state.agent.tools, 'runner') and hasattr(st.session_state.agent.tools.runner, 'tools'):
                tools = st.session_state.agent.tools.runner.tools
                st.info(f"🔧 Available MCP tools: {', '.join([tool.name for tool in tools])}")
            
        except Exception as e:
            st.error(f"❌ Failed to initialize agent: {str(e)}")
            st.error("Please check your internet connection and try again.")
            st.stop()

# Create input section
st.subheader("🔍 Search for Accommodations")

# Example queries
st.markdown("**Try these example queries:**")
col1, col2 = st.columns(2)
with col1:
    if st.button("🏖️ Beach house in Miami"):
        st.session_state.example_query = "Find me a beach house in Miami for 2 guests for next weekend"
    if st.button("🌆 NYC apartment"):
        st.session_state.example_query = "Show me apartments in Manhattan, New York for 4 guests under $200/night"

with col2:
    if st.button("🏔️ Mountain cabin"):
        st.session_state.example_query = "Find mountain cabins in Colorado for a family of 6"
    if st.button("🇫🇷 Paris studio"):
        st.session_state.example_query = "Looking for a cozy studio in Paris for 2 people"

# Main query input
query = st.text_area(
    "Enter your accommodation search request:",
    value=st.session_state.get("example_query", ""),
    placeholder="e.g., Find me a 2-bedroom apartment in Barcelona for 4 guests from July 15-20",
    height=100
)

# Search button
if st.button("🔍 Search Accommodations", type="primary"):
    if query:
        with st.spinner("🏠 Searching for accommodations..."):
            try:
                # Clear any previous example query
                if "example_query" in st.session_state:
                    del st.session_state.example_query
                
                # Make the request to the agent
                result = st.session_state.agent.start(query)
                
                if result:
                    st.subheader("🏠 Search Results")
                    st.markdown(result)
                else:
                    st.warning("⚠️ No results returned. Please try a different query.")
                    
            except Exception as e:
                st.error(f"❌ Error during search: {str(e)}")
                st.error("This might be due to MCP server connectivity issues or API limitations.")
                
                # Provide troubleshooting info
                with st.expander("🔧 Troubleshooting", expanded=True):
                    st.markdown("""
                    **Possible issues:**
                    1. **Network connectivity** - Check your internet connection
                    2. **MCP server startup** - The NPX server might take time to initialize
                    3. **API limits** - The Airbnb MCP server might have rate limits
                    4. **OpenAI API key** - Ensure OPENAI_API_KEY is set in your environment
                    
                    **To debug:**
                    - Check the Streamlit logs for detailed error messages
                    - Try running the agent outside of Streamlit first
                    - Verify the MCP server works with: `npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt`
                    """)
    else:
        st.warning("⚠️ Please enter a search query")

# Information section
with st.expander("ℹ️ About this Example", expanded=False):
    st.markdown("""
    ### Fix for Issue #459: MCP doesn't work in Streamlit
    
    **Problem**: MCP tools were not working in Streamlit applications, especially when using provider/model format like `ollama/llama3.2`.
    
    **Solution Applied**:
    1. **Use standard OpenAI model format** instead of provider/model format in Streamlit
    2. **Proper error handling** and user feedback
    3. **Session state management** for agent initialization
    4. **Verbose mode** for debugging MCP tool calls
    
    **Key Changes**:
    - Changed from `llm="ollama/llama3.2"` to `llm="gpt-4o-mini"`
    - Added proper MCP tool initialization checking
    - Implemented comprehensive error handling
    - Added debugging information for tool availability
    
    **Requirements**:
    - OpenAI API key in environment variables
    - Internet connection for NPX MCP server
    - praisonaiagents package installed
    """)

# Footer
st.markdown("---")
st.markdown("**Built with PraisonAI Agents + MCP + Streamlit** | [GitHub Issue #459](https://github.com/MervinPraison/PraisonAI/issues/459)")