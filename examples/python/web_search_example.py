"""
Unified Web Search Example

This example demonstrates the search_web tool that automatically tries
multiple search providers with fallback support.

Search Provider Priority:
1. Tavily (requires TAVILY_API_KEY + tavily-python)
2. Exa (requires EXA_API_KEY + exa_py)
3. You.com (requires YDC_API_KEY + youdotcom)
4. DuckDuckGo (requires duckduckgo_search package, no API key)
5. SearxNG (requires requests + running SearxNG instance)

Installation:
    pip install praisonaiagents duckduckgo_search

Usage:
    python web_search_example.py
"""

from praisonaiagents import Agent
from praisonaiagents.tools import search_web, get_available_providers


def main():
    print("=" * 60)
    print("Unified Web Search - Provider Status")
    print("=" * 60)
    
    # Check which providers are available
    providers = get_available_providers()
    for p in providers:
        status = "✓ Available" if p["available"] else f"✗ {p['reason']}"
        print(f"  {p['name']:12} {status}")
    
    print("\n" + "=" * 60)
    print("Example 1: Basic Search")
    print("=" * 60)
    
    # Simple search - automatically uses best available provider
    results = search_web("Python programming best practices", max_results=3)
    
    if results and "error" not in results[0]:
        print(f"\nFound {len(results)} results using {results[0].get('provider', 'unknown')}:\n")
        for r in results:
            print(f"  Title: {r.get('title', 'N/A')[:60]}...")
            print(f"  URL: {r.get('url', 'N/A')}")
            print()
    else:
        print(f"\nSearch failed: {results}")
    
    print("=" * 60)
    print("Example 2: Specify Providers")
    print("=" * 60)
    
    # Only try specific providers
    results = search_web(
        "machine learning tutorials",
        max_results=3,
        providers=["duckduckgo", "tavily"]  # Try these in order
    )
    
    if results and "error" not in results[0]:
        print(f"\nFound {len(results)} results using {results[0].get('provider', 'unknown')}:\n")
        for r in results:
            print(f"  Title: {r.get('title', 'N/A')[:60]}...")
            print(f"  URL: {r.get('url', 'N/A')}")
            print()
    else:
        print(f"\nSearch failed: {results}")
    
    print("=" * 60)
    print("Example 3: With PraisonAI Agent")
    print("=" * 60)
    
    # Use search_web as an agent tool
    agent = Agent(
        name="SearchAgent",
        role="Web Researcher",
        goal="Find and summarize information from the web",
        instructions="Search the web and provide concise summaries of findings.",
        tools=[search_web]
    )
    
    result = agent.start("What are the top 3 AI trends in 2025?")
    print(f"\nAgent Response:\n{result}")


if __name__ == "__main__":
    main()
