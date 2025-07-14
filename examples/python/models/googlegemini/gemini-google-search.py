"""
Gemini Google Search Tool Example

This example demonstrates how to use Gemini's built-in Google Search functionality
through PraisonAI. The Google Search tool allows the model to perform real-time
web searches and ground responses in current information.

Prerequisites:
- Set GEMINI_API_KEY environment variable
- Use a Gemini model that supports internal tools (gemini-2.0-flash, etc.)

Features:
- Real-time web search capabilities
- Automatic grounding of responses in search results
- No need to implement external search tools
"""

from praisonaiagents import Agent

# Ensure you have your Gemini API key set
# import os; os.environ["GEMINI_API_KEY"] = "your-api-key-here"

def main():
    # Create agent with Google Search internal tool
    agent = Agent(
        instructions="""You are a research assistant that can search the web for current information.
        Use the Google Search tool to find up-to-date information when answering questions.
        Always cite your sources and indicate when information comes from search results.""",
        
        llm="gemini/gemini-2.0-flash",
        
        # Enable Google Search internal tool
        tools=[{"googleSearch": {}}],
        
        verbose=True
    )
    
    # Example queries that benefit from real-time search
    queries = [
        "What's the latest news about AI developments this week?",
        "What's the current weather in San Francisco?",
        "What are the latest stock prices for major tech companies?",
        "What are the most recent breakthroughs in quantum computing?",
        "Who won the latest major sports championships?"
    ]
    
    print("=== Gemini Google Search Tool Demo ===\n")
    
    for i, query in enumerate(queries, 1):
        print(f"Query {i}: {query}")
        print("-" * 50)
        
        try:
            response = agent.start(query)
            print(f"Response: {response}")
            print("\n" + "="*80 + "\n")
            
        except Exception as e:
            print(f"Error: {e}")
            print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()