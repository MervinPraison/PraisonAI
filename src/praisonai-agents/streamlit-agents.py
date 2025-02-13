import streamlit as st
from praisonaiagents import Agent, Tools
from praisonaiagents.tools import duckduckgo

st.title("AI Research Assistant")
st.write("Enter your research query below to get started!")

# Initialize the research agent
agent = Agent(instructions="You are a Research Agent", tools=[duckduckgo])

# Create the input field
query = st.text_input("Research Query", placeholder="Enter your research topic...")

# Add a search button
if st.button("Search"):
    if query:
        with st.spinner("Researching..."):
            result = agent.start(query)
            st.write(result)
    else:
        st.warning("Please enter a research query")