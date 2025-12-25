"""Wikipedia Tool Example.

This example demonstrates how to use the Wikipedia tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: No API key required!
"""

from praisonai_tools import WikipediaTool


def main():
    # Initialize Wikipedia tool (no API key needed)
    wiki = WikipediaTool()
    
    # Example 1: Search Wikipedia
    print("=" * 60)
    print("Example 1: Search Wikipedia")
    print("=" * 60)
    
    results = wiki.search("Python programming", max_results=5)
    
    if results and "error" in results[0]:
        print(f"Error: {results[0]['error']}")
    else:
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  - {r['title']}")
    
    # Example 2: Get page summary
    print("\n" + "=" * 60)
    print("Example 2: Get Page Summary")
    print("=" * 60)
    
    summary = wiki.summary("Artificial intelligence", sentences=3)
    
    if "error" in summary:
        print(f"Error: {summary['error']}")
    else:
        print(f"Title: {summary['title']}")
        print(f"Summary: {summary['summary'][:300]}...")
    
    # Example 3: Get full page
    print("\n" + "=" * 60)
    print("Example 3: Get Full Page")
    print("=" * 60)
    
    page = wiki.get_page("Machine learning")
    
    if "error" in page:
        print(f"Error: {page['error']}")
        if "options" in page:
            print(f"Options: {page['options'][:5]}")
    else:
        print(f"Title: {page['title']}")
        print(f"URL: {page['url']}")
        print(f"Categories: {page['categories'][:3]}")
        print(f"Content preview: {page['content'][:200]}...")
    
    print("\n✅ Wikipedia tool working correctly!")


if __name__ == "__main__":
    main()
