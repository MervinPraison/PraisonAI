import streamlit as st
from praisonaiagents import Agent
from praisonaiagents.mcp import MCP

st.title("AI Airbnb")
st.write("Enter your research query below to get started!")

# CRITICAL: Initialize agent in session state to prevent re-initialization
if "agent" not in st.session_state:
    try:
        with st.spinner("Initializing AI agent..."):
            # Initialize agent only once and store in session state
            st.session_state.agent = Agent(
                instructions="You help book apartments on Airbnb.",
                llm="gpt-4o-mini",  # ✅ Use standard format instead of "ollama/llama3.2"
                tools=MCP("npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt"),
                verbose=True  # Enable debugging
            )
        st.success("✅ Agent initialized successfully!")
    except Exception as e:
        st.error(f"❌ Failed to initialize agent: {str(e)}")
        st.stop()

# Create the input field
query = st.text_input("Query")

# Add a search button
if st.button("Search"):
    if query:
        try:
            with st.spinner("Researching..."):
                # Use the agent from session state (already initialized)
                result = st.session_state.agent.start(query)
                st.write(result)
        except Exception as e:
            st.error(f"❌ Search failed: {str(e)}")
    else:
        st.warning("Please enter a query")

# Add troubleshooting information
with st.expander("🔧 Troubleshooting"):
    st.markdown("""
    **Key differences from problematic code:**
    
    1. **Session State**: Agent is initialized once in `st.session_state.agent`
    2. **LLM Format**: Using `"gpt-4o-mini"` instead of `"ollama/llama3.2"`
    3. **Error Handling**: Proper try-catch blocks with user feedback
    4. **Initialization Check**: Agent only created once, not on every interaction
    
    **If you still have issues:**
    - Make sure you have Node.js installed for the MCP server
    - Set your OpenAI API key: `export OPENAI_API_KEY="your-key"`
    - Try the debug mode by setting `verbose=True`
    """)