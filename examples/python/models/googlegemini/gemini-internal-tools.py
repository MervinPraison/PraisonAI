"""
Example demonstrating Gemini's internal tools:
- Google Search Grounding for real-time information
- Code Execution for computational tasks
- URL Context for web content analysis
"""

from praisonaiagents import Agent

def main():
    # Example 1: Google Search for current information
    print("=== Example 1: Google Search Grounding ===")
    search_agent = Agent(
        instructions="You are a helpful assistant that provides current information.",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "google_search_retrieval": True
        }
    )
    
    response = search_agent.start("What are the latest developments in quantum computing in 2024?")
    print(f"Response: {response}\n")
    
    # Example 2: Code Execution for data analysis
    print("=== Example 2: Code Execution ===")
    code_agent = Agent(
        instructions="You are a data analyst that can write and execute Python code.",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "enable_code_execution": True
        }
    )
    
    response = code_agent.start("""
    Create a Python script that:
    1. Generates a list of the first 20 Fibonacci numbers
    2. Calculates their sum and average
    3. Creates a simple ASCII bar chart showing their growth
    """)
    print(f"Response: {response}\n")
    
    # Example 3: Comprehensive research with all tools
    print("=== Example 3: Combined Internal Tools ===")
    research_agent = Agent(
        instructions="""You are a comprehensive research assistant that can:
        - Search the web for current information
        - Analyze web page content
        - Write and execute code for data processing""",
        llm={
            "model": "gemini/gemini-1.5-pro-latest",
            "temperature": 0.7,
            "tool_config": {
                "google_search_retrieval": {
                    "threshold": 0.8  # Higher threshold for more accurate results
                },
                "code_execution": {},
                "dynamic_retrieval_config": {
                    "mode": "grounded",
                    "dynamic_threshold": 0.6
                }
            }
        },
        verbose=True  # Show detailed execution
    )
    
    response = research_agent.start("""
    Please help me understand the current state of renewable energy:
    1. Search for the latest statistics on global renewable energy adoption
    2. If you find any relevant URLs, analyze their content
    3. Write Python code to visualize the key statistics you found
    """)
    print(f"Response: {response}")

if __name__ == "__main__":
    main()