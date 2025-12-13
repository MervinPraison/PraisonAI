import streamlit as st
import os
from praisonaiagents import Agent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Agentic RAG with GPT-5",
    page_icon="🧠",
    layout="wide"
)

# Main title and description
st.title("🧠 Agentic RAG with GPT-5")
st.markdown("""
This app demonstrates an intelligent AI agent that:
1. **Answers** your questions clearly and concisely using GPT-5

⚠️ **Note**: Knowledge base functionality is temporarily disabled due to a compatibility issue with the current version of PraisonAI Agents.

Enter your OpenAI API key in the sidebar to get started!
""")

# Sidebar for API key and settings
with st.sidebar:
    st.header("🔧 Configuration")
    
    # OpenAI API Key
    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=os.getenv("OPENAI_API_KEY", ""),
        help="Get your key from https://platform.openai.com/"
    )

    # Add URLs to knowledge base
    st.subheader("🌐 Add Knowledge Sources")
    st.info("⚠️ Knowledge base functionality is temporarily disabled due to compatibility issues.")
    new_url = st.text_input(
        "Add URL",
        placeholder="https://docs.praisonai.com/introduction",
        help="Enter a URL to add to the knowledge base (currently disabled)"
    )
    
    if st.button("➕ Add URL", type="primary", disabled=True):
        st.info("Knowledge base functionality is temporarily disabled.")

# Check if API key is provided
if openai_key:
    # Initialize knowledge base (cached to avoid reloading)
    @st.cache_resource(show_spinner="📚 Loading knowledge base...")
    def load_knowledge() -> list:
        """Load and initialize the knowledge base with default URL"""
        return ["https://docs.praisonai.com/introduction/agents.md"]  # Default URL

    # Initialize agent (cached to avoid reloading)
    @st.cache_resource(show_spinner="🤖 Loading agent...")
    def load_agent(_knowledge: list) -> Agent:
        """Create an agent with reasoning capabilities"""
        # Note: Temporarily removed knowledge parameter to avoid rerank error
        # TODO: Re-enable when PraisonAI Agents knowledge issue is resolved
        return Agent(
            name="Knowledge Agent",
            instructions=[
                "You are a helpful AI assistant. Answer questions based on your general knowledge.",
                "Provide clear, well-structured answers in markdown format.",
                "Use proper markdown formatting with headers, lists, and emphasis where appropriate.",
                "Structure your response with clear sections and bullet points when helpful.",
            ],
            llm="gpt-5-nano
            markdown=True,
            verbose=True
        )

    # Load knowledge and agent
    knowledge = load_knowledge()
    agent = load_agent(knowledge)
    
    # Display current URLs in knowledge base
    if knowledge:
        st.sidebar.subheader("📚 Current Knowledge Sources")
        for i, url in enumerate(knowledge, 1):
            st.sidebar.markdown(f"{i}. {url}")
    
    # Handle URL additions
    if hasattr(st.session_state, 'urls_to_add') and st.session_state.urls_to_add:
        with st.spinner("📥 Loading new documents..."):
            knowledge.append(st.session_state.urls_to_add)
            # Reinitialize agent with new knowledge
            agent = load_agent(knowledge)
        st.success(f"✅ Added: {st.session_state.urls_to_add}")
        del st.session_state.urls_to_add
        st.rerun()

    # Main query section
    st.divider()
    st.subheader("🤔 Ask a Question")
    
    # Suggested prompts
    st.markdown("**Try these prompts:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("What is PraisonAI?", use_container_width=True):
            st.session_state.query = "What is PraisonAI and how do Agents work?"
    with col2:
        if st.button("Teams in PraisonAI", use_container_width=True):
            st.session_state.query = "What are Teams in PraisonAI and how do they work?"
    with col3:
        if st.button("Build RAG system", use_container_width=True):
            st.session_state.query = "Give me a step-by-step guide to building a RAG system."
    
    # Query input
    query = st.text_area(
        "Your question:",
        value=st.session_state.get("query", "What are AI Agents?"),
        height=100,
        help="Ask anything about the loaded knowledge sources"
    )
    
    # Run button
    if st.button("🚀 Get Answer", type="primary"):
        if query:
            # Create container for answer
            st.markdown("### 💡 Answer")
            answer_container = st.container()
            answer_placeholder = answer_container.empty()
            
            # Get the agent's response
            with st.spinner("🔍 Searching and generating answer..."):
                try:
                    st.info("🤖 Agent is processing your question...")
                    response = agent.start(query)
                    answer_placeholder.markdown(
                        response, 
                        unsafe_allow_html=True
                    )
                except Exception as e:
                    st.error(f"Error getting response: {str(e)}")
                    st.error(f"Error type: {type(e).__name__}")
                    st.error(f"Full error details: {repr(e)}")
                    # Try to provide a helpful response
                    answer_placeholder.markdown("""
                    **⚠️ Error occurred while processing your question.**
                    
                    This might be due to:
                    - Knowledge base configuration issues
                    - Model access problems
                    - Network connectivity issues
                    
                    Please try again or check your OpenAI API key.
                    """)
        else:
            st.error("Please enter a question")

else:
    # Show instructions if API key is missing
    st.info("""
    👋 **Welcome! To use this app, you need:**
    
    - **OpenAI API Key** (set it in the sidebar)
      - Sign up at [platform.openai.com](https://platform.openai.com/)
      - Generate a new API key
    
    Once you enter the key, the app will load the knowledge base and agent.
    """)

# Footer with explanation
st.divider()
with st.expander("📖 How This Works"):
    st.markdown("""
    **This app uses the PraisonAI Agents framework to create an intelligent Q&A system:**
    
    ⚠️ **Current Status**: Knowledge base functionality is temporarily disabled due to compatibility issues with the current version of PraisonAI Agents (v0.0.157).
    
    **What Works Now:**
    1. **GPT-5 Integration**: OpenAI's GPT-5 model for generating intelligent responses
    2. **Markdown Formatting**: Beautiful, structured responses
    3. **Agent Framework**: PraisonAI Agents for orchestration
    
    **What's Temporarily Disabled:**
    - URL-based knowledge base
    - Vector search and retrieval
    - Document processing
    
    **Key Components:**
    - `Agent`: PraisonAI Agents framework for creating intelligent agents
    - `llm`: OpenAI GPT-5-nano for generating responses
    
    **Why PraisonAI Agents?**
    - Easy-to-use agent framework
    - Built-in error handling
    - Clean API design
    - Perfect for prototyping and production applications
    
    **Next Steps:**
    - Monitor PraisonAI Agents updates for knowledge base fixes
    - Re-enable knowledge functionality when compatible version is available
    """)
