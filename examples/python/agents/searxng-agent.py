#!/usr/bin/env python3
"""
SearxNG Search Agent Example

A simple example showing how to create an agent that uses SearxNG for web searches.
This provides privacy-focused search capabilities as an alternative to traditional search engines.

Prerequisites:
1. Install dependencies: pip install requests
2. Run SearxNG: docker run -d --name searxng -p 32768:8080 searxng/searxng
"""

from praisonaiagents import Agent, Task
from praisonaiagents.tools import searxng_search

def main():
    """Create and run a SearxNG-enabled search agent"""
    
    # Create a search agent with SearxNG capabilities
    search_agent = Agent(
        name="Privacy Search Agent",
        instructions="""You are a privacy-focused search assistant that uses SearxNG to find information.
        
        Your capabilities:
        - Search the web using SearxNG for privacy-focused results
        - Analyze and summarize search findings
        - Provide relevant links and sources
        - Respect user privacy by using local SearxNG instance
        
        When searching:
        1. Use relevant keywords to get the best results
        2. Analyze the search results for quality and relevance
        3. Provide a clear summary with key points
        4. Include important URLs for further reading
        5. If search fails, explain the issue and suggest alternatives""",
        tools=[searxng_search]
    )
    
    # Create search tasks
    tasks = [
        Task(
            description="Search for information about renewable energy technologies and provide a comprehensive summary",
            agent=search_agent
        ),
        Task(
            description="Find the latest news about artificial intelligence developments in 2024",
            agent=search_agent
        ),
        Task(
            description="Research privacy-focused alternatives to mainstream social media platforms",
            agent=search_agent
        )
    ]
    
    print("Privacy Search Agent - Using SearxNG")
    print("=" * 50)
    
    # Execute each task
    for i, task in enumerate(tasks, 1):
        print(f"\n🔍 Task {i}: {task.description}")
        print("-" * 50)
        
        try:
            result = task.execute()
            print(f"Result:\n{result}")
        except Exception as e:
            print(f"❌ Task failed: {e}")
            print("Make sure SearxNG is running at http://localhost:32768")
        
        print("\n" + "=" * 50)
    
    print("\n✅ All search tasks completed!")
    print("\nSearxNG Benefits:")
    print("• Privacy-focused: No tracking or data collection")
    print("• Multi-engine: Aggregates results from multiple sources")
    print("• Self-hosted: Full control over your search infrastructure")
    print("• Customizable: Configure engines and settings as needed")

if __name__ == "__main__":
    main()