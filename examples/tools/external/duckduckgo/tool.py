"""DuckDuckGo Search Tool Example.

This example demonstrates how to use the DuckDuckGo search tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: No API key required!
"""

from praisonai_tools import DuckDuckGoTool


def main():
    # Initialize DuckDuckGo tool (no API key needed)
    ddg = DuckDuckGoTool()
    
    # Example 1: Web search
    print("=" * 60)
    print("Example 1: Web Search")
    print("=" * 60)
    
    results = ddg.search("Python programming best practices", max_results=3)
    
    if results and "error" in results[0]:
        print(f"Error: {results[0]['error']}")
    else:
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  - {r['title']}")
            print(f"    URL: {r['url']}")
            print(f"    Snippet: {r['snippet'][:100]}...")
            print()
    
    # Example 2: News search
    print("=" * 60)
    print("Example 2: News Search")
    print("=" * 60)
    
    news = ddg.news("artificial intelligence", max_results=3)
    
    if news and "error" in news[0]:
        print(f"Error: {news[0]['error']}")
    else:
        print(f"Found {len(news)} news articles:")
        for n in news:
            print(f"  - {n['title']}")
            print(f"    Source: {n.get('source', 'N/A')}")
            print(f"    Date: {n.get('date', 'N/A')}")
            print()
    
    # Example 3: Image search
    print("=" * 60)
    print("Example 3: Image Search")
    print("=" * 60)
    
    images = ddg.images("sunset landscape", max_results=3)
    
    if images and "error" in images[0]:
        print(f"Error: {images[0]['error']}")
    else:
        print(f"Found {len(images)} images:")
        for img in images:
            print(f"  - {img['title']}")
            print(f"    Image URL: {img['image_url'][:60]}...")
            print()
    
    print("✅ DuckDuckGo tool working correctly!")


if __name__ == "__main__":
    main()
