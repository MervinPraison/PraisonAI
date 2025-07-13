"""
Async example demonstrating how to use Gemini's internal tools:
- Google Search Grounding
- Code Execution
- URL Context (Dynamic Retrieval)
"""

import asyncio
from praisonaiagents import Agent

async def main():
    # Example 1: Async Google Search Grounding
    print("=== Example 1: Async Google Search Grounding ===")
    search_agent = Agent(
        instructions="You are a helpful assistant that can search the web for current information.",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "google_search_retrieval": True  # Enable Google Search
        }
    )

    response = await search_agent.astart("What are the latest developments in AI today?")
    print(f"Search Agent Response: {response}\n")

    # Example 2: Async Code Execution
    print("=== Example 2: Async Code Execution ===")
    code_agent = Agent(
        instructions="You are a data analysis assistant that can write and execute Python code.",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "enable_code_execution": True  # Enable code execution
        }
    )

    response = await code_agent.astart("""
    Create a Python script that:
    1. Generates 100 random numbers between 1 and 100
    2. Calculates mean, median, and standard deviation
    3. Creates a simple histogram visualization (as ASCII art)
    """)
    print(f"Code Agent Response: {response}\n")

    # Example 3: Parallel execution with multiple agents
    print("=== Example 3: Parallel Async Execution ===")
    
    # Create multiple agents with different internal tools
    agents_config = [
        {
            "name": "Search Agent",
            "agent": Agent(
                instructions="Search for latest Python news",
                llm={"model": "gemini/gemini-1.5-flash", "google_search_retrieval": True}
            ),
            "prompt": "What are the latest updates in Python 3.13?"
        },
        {
            "name": "Code Agent",
            "agent": Agent(
                instructions="Execute Python code",
                llm={"model": "gemini/gemini-1.5-flash", "enable_code_execution": True}
            ),
            "prompt": "Write and run code to check if 2024 is a leap year"
        },
        {
            "name": "URL Agent",
            "agent": Agent(
                instructions="Analyze web content",
                llm={
                    "model": "gemini/gemini-1.5-flash",
                    "dynamic_retrieval_config": {"mode": "grounded"}
                }
            ),
            "prompt": "What does the Python.org homepage say about getting started with Python?"
        }
    ]

    # Execute all agents in parallel
    tasks = [
        agent_config["agent"].astart(agent_config["prompt"]) 
        for agent_config in agents_config
    ]
    
    results = await asyncio.gather(*tasks)
    
    for agent_config, result in zip(agents_config, results):
        print(f"{agent_config['name']} Result: {result[:200]}...\n")

    # Example 4: Advanced async workflow with tool chaining
    print("=== Example 4: Advanced Async Workflow ===")
    advanced_agent = Agent(
        instructions="""You are an advanced research assistant with access to multiple capabilities.
        You can search the web, execute code, and analyze URLs.""",
        llm={
            "model": "gemini/gemini-1.5-pro-latest",
            "temperature": 0.7,
            "tool_config": {
                "google_search_retrieval": {"threshold": 0.8},
                "code_execution": {},
                "dynamic_retrieval_config": {"mode": "grounded", "dynamic_threshold": 0.6}
            }
        }
    )

    response = await advanced_agent.astart("""
    Please help me with a comprehensive analysis:
    1. Search for the current Bitcoin price
    2. If you find any financial website URLs, analyze them for additional market data
    3. Write Python code to calculate the percentage change if Bitcoin reaches $100,000
    4. Create a simple prediction based on current trends
    """)
    print(f"Advanced Agent Response: {response}")

if __name__ == "__main__":
    asyncio.run(main())