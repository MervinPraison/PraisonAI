"""
Example demonstrating how to use Gemini's internal tools:
- Google Search Grounding
- Code Execution
- URL Context (Dynamic Retrieval)
"""

from praisonaiagents import Agent

# Example 1: Google Search Grounding
print("=== Example 1: Google Search Grounding ===")
search_agent = Agent(
    instructions="You are a helpful assistant that can search the web for current information.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True  # Enable Google Search
    }
)

response = search_agent.start("What is the current weather in Tokyo today?")
print(f"Search Agent Response: {response}\n")

# Example 2: Code Execution
print("=== Example 2: Code Execution ===")
code_agent = Agent(
    instructions="You are a coding assistant that can write and execute Python code.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "enable_code_execution": True  # Enable code execution
    }
)

response = code_agent.start("Calculate the 10th Fibonacci number using Python code")
print(f"Code Agent Response: {response}\n")

# Example 3: URL Context (Dynamic Retrieval)
print("=== Example 3: URL Context ===")
url_agent = Agent(
    instructions="You are a web content analyzer that can read and analyze web pages.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "dynamic_retrieval_config": {
            "mode": "grounded",
            "dynamic_threshold": 0.5
        }
    }
)

response = url_agent.start("Analyze the content at https://www.python.org and tell me about the latest Python version mentioned")
print(f"URL Agent Response: {response}\n")

# Example 4: Combined Tools
print("=== Example 4: Combined Internal Tools ===")
research_agent = Agent(
    instructions="""You are a research assistant that can:
    1. Search the web for current information
    2. Analyze content from URLs
    3. Write and execute Python code for data analysis
    """,
    llm={
        "model": "gemini/gemini-1.5-pro-latest",
        "temperature": 0.7,
        "max_tokens": 2000,
        "tool_config": {
            "google_search_retrieval": {
                "threshold": 0.7
            },
            "code_execution": {},
            "dynamic_retrieval_config": {
                "mode": "grounded",
                "dynamic_threshold": 0.5
            }
        }
    },
    verbose=True
)

response = research_agent.start("""
Search for the current stock price of Apple (AAPL), 
then write Python code to calculate what percentage increase it would be if it reaches $250.
""")
print(f"Research Agent Response: {response}\n")

# Example 5: Using with Custom Tools alongside Internal Tools
print("=== Example 5: Custom Tools + Internal Tools ===")

def get_current_time():
    """Get the current time"""
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

hybrid_agent = Agent(
    instructions="You are an assistant that can use both custom tools and Gemini's internal capabilities.",
    llm={
        "model": "gemini/gemini-1.5-flash",
        "google_search_retrieval": True,
        "enable_code_execution": True
    },
    tools=[get_current_time]  # Custom tool
)

response = hybrid_agent.start("""
First, tell me the current time using the tool.
Then, search the web for today's top tech news.
Finally, write Python code to create a simple summary statistics of the word counts.
""")
print(f"Hybrid Agent Response: {response}")