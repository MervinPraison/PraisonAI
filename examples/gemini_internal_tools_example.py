#!/usr/bin/env python3
"""
Example: Using Gemini's Internal Tools

This example demonstrates how to use Gemini's built-in tools:
- Google Search Retrieval: For real-time web search
- Code Execution: For running Python code

Note: Requires a Gemini API key set as GOOGLE_API_KEY environment variable
"""

from praisonaiagents import Agent, Task, PraisonAIAgents

# Example 1: Research Agent with Google Search
research_agent = Agent(
    name="Research Assistant",
    role="Web Researcher",
    goal="Find accurate and up-to-date information from the web",
    backstory="You are an expert researcher who can find and synthesize information from various sources",
    llm="gemini/gemini-2.0-flash",
    gemini_google_search=True,  # Enable Google Search grounding
    verbose=True
)

# Example 2: Data Analysis Agent with Code Execution
analyst_agent = Agent(
    name="Data Analyst",
    role="Python Developer and Data Analyst",
    goal="Analyze data and perform calculations using Python",
    backstory="You are an experienced data analyst who can write and execute Python code to solve problems",
    llm="gemini/gemini-2.0-flash",
    gemini_code_execution=True,  # Enable code execution
    verbose=True
)

# Example 3: Full-Featured Agent with Both Tools
full_agent = Agent(
    name="AI Assistant",
    role="General Purpose Assistant",
    goal="Help users with research and computational tasks",
    backstory="You are a versatile AI assistant with access to web search and code execution capabilities",
    llm="gemini/gemini-2.0-flash",
    gemini_google_search=True,   # Enable Google Search
    gemini_code_execution=True,   # Enable code execution
    verbose=True
)

# Example Tasks

# Task 1: Research current events
research_task = Task(
    name="research_task",
    description="Find the latest information about renewable energy developments in 2024",
    expected_output="A summary of recent renewable energy news and developments",
    agent=research_agent
)

# Task 2: Perform calculations
analysis_task = Task(
    name="analysis_task",
    description="Calculate the compound interest on $10,000 invested at 5% annual rate for 10 years",
    expected_output="The calculated amount with detailed breakdown",
    agent=analyst_agent
)

# Task 3: Research and analyze
combined_task = Task(
    name="combined_task",
    description="Find the current Bitcoin price and calculate how much $1000 would buy",
    expected_output="Current BTC price and the amount of Bitcoin that can be purchased",
    agent=full_agent
)

# Run individual agents
if __name__ == "__main__":
    print("=== Example 1: Research with Google Search ===")
    research_agent.start("What are the latest developments in AI in 2024?")
    
    print("\n=== Example 2: Code Execution ===")
    analyst_agent.start("Create a Python function to calculate factorial and test it with 5")
    
    print("\n=== Example 3: Combined Capabilities ===")
    full_agent.start("Search for the current weather in Tokyo and write Python code to convert it from Celsius to Fahrenheit")
    
    print("\n=== Example 4: Multi-Agent Workflow ===")
    # Create a workflow with multiple agents
    workflow = PraisonAIAgents(
        agents=[research_agent, analyst_agent],
        tasks=[research_task, analysis_task],
        process="sequential",
        verbose=True
    )
    
    # Run the workflow
    result = workflow.start()
    print(f"\nWorkflow completed with result: {result}")