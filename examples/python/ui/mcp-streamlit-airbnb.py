import streamlit as st
from praisonaiagents import Agent
from praisonaiagents.mcp import MCP
import logging
import traceback

# Configure page
st.set_page_config(
    page_title="AI Airbnb Assistant",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 AI Airbnb Assistant")
st.write("Enter your accommodation search query below to get started!")

# Add configuration options in sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # LLM Model Selection
    llm_model = st.selectbox(
        "Choose LLM Model",
        options=[
            "gpt-4o-mini",
            "gpt-4o", 
            "gpt-3.5-turbo",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022"
        ],
        index=0,
        help="Select the language model to use. Avoid provider/model format like 'ollama/llama3.2' in Streamlit."
    )
    
    # Debug Mode
    debug_mode = st.checkbox(
        "Enable Debug Mode",
        value=False,
        help="Enable detailed logging for troubleshooting"
    )
    
    # MCP Server Command
    mcp_command = st.text_input(
        "MCP Server Command",
        value="npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt",
        help="The command to start the MCP server"
    )

# Initialize session state
if "agent_initialized" not in st.session_state:
    st.session_state.agent_initialized = False
    st.session_state.agent = None
    st.session_state.init_error = None

# Function to initialize agent
def initialize_agent():
    """Initialize the agent with proper error handling."""
    try:
        with st.spinner("🔄 Initializing AI agent and MCP tools..."):
            if debug_mode:
                st.info("🐛 Debug mode enabled - check console for detailed logs")
                
            # Create MCP tools
            mcp_tools = MCP(
                mcp_command,
                timeout=60,
                debug=debug_mode
            )
            
            # Create agent with session state management
            agent = Agent(
                instructions="""You are a helpful Airbnb assistant. Help users find and book apartments. 
                Use the available tools to search for accommodations, get property details, and provide helpful recommendations.
                Always be polite and provide comprehensive information about properties.""",
                llm=llm_model,
                tools=mcp_tools,
                verbose=debug_mode
            )
            
            return agent, None
            
    except Exception as e:
        error_msg = f"Failed to initialize agent: {str(e)}"
        if debug_mode:
            error_msg += f"\n\nFull traceback:\n{traceback.format_exc()}"
        return None, error_msg

# Agent initialization section
if not st.session_state.agent_initialized:
    if st.button("🚀 Initialize AI Assistant", type="primary"):
        agent, error = initialize_agent()
        
        if agent:
            st.session_state.agent = agent
            st.session_state.agent_initialized = True
            st.session_state.init_error = None
            st.success("✅ AI Assistant initialized successfully!")
            st.rerun()
        else:
            st.session_state.init_error = error
            st.error(f"❌ Initialization failed: {error}")

# Show initialization status
if st.session_state.init_error:
    st.error(f"❌ Initialization Error: {st.session_state.init_error}")
    
    with st.expander("🔧 Troubleshooting Tips"):
        st.markdown("""
        **Common issues and solutions:**
        
        1. **MCP Server Issues:**
           - Ensure Node.js and npm are installed
           - Check if the MCP server command is correct
           - Try running the MCP command manually first
        
        2. **LLM Model Issues:**
           - Make sure you have API keys set as environment variables
           - Avoid provider/model formats (e.g., "ollama/llama3.2") in Streamlit
           - Use standard model names (e.g., "gpt-4o-mini")
        
        3. **Network/Timeout Issues:**
           - Check your internet connection
           - Increase timeout if needed
           - Enable debug mode for more details
        
        4. **Environment Issues:**
           - Make sure all required packages are installed
           - Check Python version compatibility
        """)

# Main chat interface (only show if agent is initialized)
if st.session_state.agent_initialized and st.session_state.agent:
    st.success("✅ AI Assistant is ready!")
    
    # Create two columns for better layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Query input
        query = st.text_area(
            "🔍 What are you looking for?",
            placeholder="e.g., 'Find a 2-bedroom apartment in Paris for next weekend' or 'Show me luxury stays in Tokyo under $200/night'",
            height=100
        )
        
        # Search button
        search_col1, search_col2 = st.columns([1, 4])
        with search_col1:
            search_button = st.button("🔍 Search", type="primary", use_container_width=True)
    
    with col2:
        # Tips and examples
        with st.container():
            st.markdown("### 💡 Tips")
            st.markdown("""
            - Be specific about location and dates
            - Mention budget preferences
            - Include number of guests
            - Ask about amenities
            """)
            
            with st.expander("📝 Example Queries"):
                st.markdown("""
                - "Find a beachfront apartment in Barcelona for 4 people"
                - "Show me pet-friendly stays in London under £150/night"
                - "I need a place with a kitchen near downtown Tokyo"
                - "Find luxury accommodations in NYC for a business trip"
                """)

    # Handle search
    if search_button and query:
        if not query.strip():
            st.warning("⚠️ Please enter a search query")
        else:
            try:
                with st.spinner("🔍 Searching for accommodations..."):
                    # Add query to chat history
                    if "chat_history" not in st.session_state:
                        st.session_state.chat_history = []
                    
                    st.session_state.chat_history.append({"role": "user", "content": query})
                    
                    # Get response from agent
                    result = st.session_state.agent.start(query)
                    
                    st.session_state.chat_history.append({"role": "assistant", "content": result})
                    
                    # Display result
                    st.markdown("### 🏠 Search Results")
                    st.markdown(result)
                    
            except Exception as e:
                error_msg = f"Search failed: {str(e)}"
                st.error(f"❌ {error_msg}")
                
                if debug_mode:
                    st.error(f"Full traceback:\n{traceback.format_exc()}")
    
    # Chat history section
    if "chat_history" in st.session_state and st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### 💬 Conversation History")
        
        for i, message in enumerate(st.session_state.chat_history):
            if message["role"] == "user":
                st.markdown(f"**🙋 You:** {message['content']}")
            else:
                st.markdown(f"**🤖 Assistant:** {message['content']}")
            
            if i < len(st.session_state.chat_history) - 1:
                st.markdown("---")
        
        # Clear history button
        if st.button("🗑️ Clear History"):
            st.session_state.chat_history = []
            st.rerun()

else:
    # Show instructions for first-time users
    st.info("👆 Please initialize the AI Assistant first using the button above.")
    
    with st.expander("ℹ️ About this Application"):
        st.markdown("""
        This Streamlit application demonstrates how to properly integrate MCP (Model Context Protocol) 
        tools with PraisonAI Agents in a Streamlit environment.
        
        **Key Features:**
        - ✅ Proper session state management for Streamlit
        - ✅ Comprehensive error handling and user feedback
        - ✅ Debug mode for troubleshooting
        - ✅ Flexible LLM model selection
        - ✅ Clean and intuitive user interface
        
        **Technical Implementation:**
        - Uses session state to prevent agent re-initialization
        - Implements proper error handling for MCP setup
        - Provides detailed troubleshooting guidance
        - Demonstrates best practices for Streamlit + MCP integration
        """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        Built with PraisonAI Agents + MCP • 
        <a href='https://github.com/MervinPraison/PraisonAI' target='_blank'>GitHub</a> • 
        <a href='https://docs.praisonai.com' target='_blank'>Documentation</a>
    </div>
    """, 
    unsafe_allow_html=True
)