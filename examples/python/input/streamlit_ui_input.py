"""
Streamlit UI Input Example for PraisonAI

This example demonstrates how to create a web-based UI for dynamic user input
using Streamlit, making it easy for users to interact with PraisonAI agents.

To run this example:
1. Install streamlit: pip install streamlit
2. Run: streamlit run streamlit_ui_input.py
"""

import streamlit as st
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

# Set page configuration
st.set_page_config(
    page_title="PraisonAI Dynamic Input",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 PraisonAI Dynamic Input Interface")
st.markdown("---")

# Create sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Model selection
    model = st.selectbox(
        "Select Model",
        ["gpt-5-nano", "gpt-5-mini", "gpt-3.5-turbo", "claude-3-opus"],
        index=0
    )
    
    # Temperature slider
    temperature = st.slider(
        "Creativity Level (Temperature)",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.1
    )
    
    # Process type
    process_type = st.radio(
        "Process Type",
        ["sequential", "hierarchical"],
        index=0
    )
    
    # Enable tools
    use_tools = st.checkbox("Enable Web Search", value=True)

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    # User input
    user_query = st.text_area(
        "What would you like to know?",
        placeholder="Enter your question or research topic here...",
        height=100
    )
    
    # Additional options
    with st.expander("Advanced Options"):
        max_search_results = st.number_input(
            "Max Search Results",
            min_value=1,
            max_value=20,
            value=5
        )
        
        output_format = st.selectbox(
            "Output Format",
            ["Summary", "Detailed Report", "Bullet Points"],
            index=0
        )
        
        include_sources = st.checkbox("Include Sources", value=True)

with col2:
    st.info(
        "💡 **Tips:**\n"
        "- Be specific with your questions\n"
        "- Use higher temperature for creative tasks\n"
        "- Enable web search for current information"
    )

# Submit button
if st.button("🚀 Submit", type="primary", use_container_width=True):
    if user_query:
        # Create progress container
        progress_container = st.container()
        
        with progress_container:
            with st.spinner("🔄 Processing your request..."):
                try:
                    # Create agent with dynamic configuration
                    agent = Agent(
                        name="Assistant",
                        role=f"{output_format} Specialist",
                        goal=f"Answer: {user_query}",
                        backstory="Knowledgeable assistant with configurable capabilities",
                        tools=[duckduckgo] if use_tools else [],
                        llm={
                            "model": model,
                            "temperature": temperature
                        }
                    )
                    
                    # Create task with dynamic parameters
                    task_description = f"Provide a {output_format.lower()} answer for: {user_query}"
                    if use_tools:
                        task_description += f"\nSearch for up to {max_search_results} relevant results."
                    if include_sources:
                        task_description += "\nInclude sources for all information."
                    
                    task = Task(
                        description=task_description,
                        expected_output=f"{output_format} with clear, helpful information",
                        agent=agent
                    )
                    
                    # Run agents
                    agents = PraisonAIAgents(
                        agents=[agent],
                        tasks=[task],
                        process=process_type
                    )
                    
                    result = agents.start()
                    
                    # Display results
                    st.success("✅ Processing complete!")
                    
                    # Show result in a nice format
                    st.markdown("### 📊 Results")
                    
                    # Create tabs for different views
                    tab1, tab2, tab3 = st.tabs(["Result", "Configuration", "Raw Output"])
                    
                    with tab1:
                        st.markdown(result)
                    
                    with tab2:
                        st.json({
                            "model": model,
                            "temperature": temperature,
                            "process": process_type,
                            "tools_enabled": use_tools,
                            "output_format": output_format,
                            "query": user_query
                        })
                    
                    with tab3:
                        st.code(result, language="markdown")
                    
                    # Download button
                    st.download_button(
                        label="📥 Download Results",
                        data=result,
                        file_name=f"{user_query[:30].replace(' ', '_')}_results.txt",
                        mime="text/plain"
                    )
                    
                except Exception as e:
                    st.error(f"❌ An error occurred: {str(e)}")
                    st.exception(e)
    else:
        st.warning("⚠️ Please enter a question or topic to research.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using PraisonAI and Streamlit")