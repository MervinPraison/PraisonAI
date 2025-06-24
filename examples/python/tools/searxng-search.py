#!/usr/bin/env python3
"""
SearxNG Search Tool Example

This example demonstrates how to use the SearxNG search tool for privacy-focused web searches.
Make sure you have a SearxNG instance running locally before running this example.

Prerequisites:
1. Install dependencies: pip install requests
2. Run SearxNG: docker run -d --name searxng -p 32768:8080 searxng/searxng
3. Wait a moment for SearxNG to start up
"""

from praisonaiagents import Agent, Task, Process
from praisonaiagents.tools import searxng_search

def basic_search_example():
    """Basic SearxNG search example"""
    print("=== Basic SearxNG Search ===")
    
    # Simple search
    results = searxng_search("Python programming tutorials", max_results=3)
    
    for i, result in enumerate(results, 1):
        if "error" in result:
            print(f"Error: {result['error']}")
            break
        else:
            print(f"\n{i}. {result['title']}")
            print(f"   URL: {result['url']}")
            print(f"   Snippet: {result['snippet'][:100]}...")

def agent_search_example():
    """Example using SearxNG with an agent"""
    print("\n=== Agent-Based SearxNG Search ===")
    
    # Create a research agent
    researcher = Agent(
        name="Research Agent",
        instructions="""You are a research assistant that uses SearxNG to find information.
        When searching, provide a comprehensive summary of the findings including:
        1. Key points from the search results
        2. Relevant URLs for further reading
        3. Your analysis of the information quality""",
        tools=[searxng_search]
    )
    
    # Create a task
    task = Task(
        description="Search for information about sustainable energy technologies and provide a summary",
        agent=researcher
    )
    
    # Execute the task
    result = task.execute()
    print(f"Research Result:\n{result}")

def multi_search_example():
    """Example with multiple searches using different parameters"""
    print("\n=== Multi-Search Example ===")
    
    queries = [
        ("artificial intelligence news", 3),
        ("climate change solutions", 3),
        ("quantum computing basics", 2)
    ]
    
    for query, max_results in queries:
        print(f"\nSearching for: '{query}'")
        results = searxng_search(query, max_results=max_results)
        
        if results and "error" not in results[0]:
            print(f"Found {len(results)} results:")
            for result in results:
                print(f"  • {result['title']}")
        else:
            print(f"  Error or no results: {results}")

def custom_searxng_url_example():
    """Example using custom SearxNG URL"""
    print("\n=== Custom SearxNG URL Example ===")
    
    # Example with different SearxNG instances
    searxng_instances = [
        "http://localhost:32768/search",  # Default local instance
        "http://localhost:8080/search",   # Alternative port
    ]
    
    query = "machine learning"
    
    for url in searxng_instances:
        print(f"\nTrying SearxNG at: {url}")
        results = searxng_search(query, max_results=2, searxng_url=url)
        
        if results and "error" not in results[0]:
            print(f"✅ Success! Found {len(results)} results")
            for result in results:
                print(f"  • {result['title']}")
        else:
            print(f"❌ Failed: {results[0].get('error', 'Unknown error') if results else 'No results'}")

def multi_agent_research_example():
    """Advanced example with multiple agents using SearxNG"""
    print("\n=== Multi-Agent Research System ===")
    
    # Create specialized agents
    tech_researcher = Agent(
        name="Tech Researcher",
        instructions="Search for technical and scientific information. Focus on accuracy and technical depth.",
        tools=[searxng_search]
    )
    
    news_analyst = Agent(
        name="News Analyst", 
        instructions="Search for current news and trends. Provide timely and relevant information.",
        tools=[searxng_search]
    )
    
    # Create tasks
    tech_task = Task(
        description="Research the latest developments in artificial intelligence and machine learning",
        agent=tech_researcher
    )
    
    news_task = Task(
        description="Find recent news about AI adoption in healthcare",
        agent=news_analyst
    )
    
    # Create process
    process = Process(
        agents=[tech_researcher, news_analyst],
        tasks=[tech_task, news_task]
    )
    
    # Execute
    try:
        result = process.run()
        print(f"Multi-agent research completed:\n{result}")
    except Exception as e:
        print(f"Process execution error: {e}")

def error_handling_example():
    """Example demonstrating error handling"""
    print("\n=== Error Handling Example ===")
    
    # Test with invalid URL
    print("Testing with invalid SearxNG URL...")
    results = searxng_search("test query", searxng_url="http://invalid-url:9999/search")
    
    if results and "error" in results[0]:
        print(f"Expected error caught: {results[0]['error']}")
    
    # Test with valid URL but empty query
    print("\nTesting with empty query...")
    results = searxng_search("", max_results=1)
    
    if results:
        if "error" in results[0]:
            print(f"Error for empty query: {results[0]['error']}")
        else:
            print(f"Unexpected success with empty query: {len(results)} results")

def main():
    """Main function to run all examples"""
    print("SearxNG Search Tool Examples")
    print("=" * 50)
    
    # Check if requests is available
    try:
        import requests
        print("✅ requests package is available")
    except ImportError:
        print("❌ requests package not found. Install with: pip install requests")
        return
    
    try:
        # Run examples
        basic_search_example()
        agent_search_example()
        multi_search_example()
        custom_searxng_url_example()
        multi_agent_research_example()
        error_handling_example()
        
        print("\n" + "=" * 50)
        print("✅ All examples completed!")
        print("\nTips for using SearxNG:")
        print("• Ensure your SearxNG instance is running and accessible")
        print("• Configure SearxNG engines and settings as needed")
        print("• Use environment variables for different deployment URLs")
        print("• Implement proper error handling in production code")
        
    except Exception as e:
        print(f"\n❌ Example execution error: {e}")
        print("Make sure SearxNG is running at http://localhost:32768")

if __name__ == "__main__":
    main()