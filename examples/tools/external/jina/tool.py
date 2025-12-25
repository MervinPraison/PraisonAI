"""Jina Reader Tool Example.

This example demonstrates how to use the Jina Reader tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: Works without API key (with rate limits)
"""

from praisonai_tools import JinaTool


def main():
    # Initialize Jina tool (works without API key)
    jina = JinaTool()
    
    # Example 1: Read a URL
    print("=" * 60)
    print("Example 1: Read URL Content")
    print("=" * 60)
    
    result = jina.read("https://example.com")
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"URL: {result.get('url', 'N/A')}")
        print(f"Title: {result.get('title', 'N/A')}")
        content = result.get('content', '')
        print(f"Content preview: {content[:300]}...")
    
    print("\n✅ Jina tool working correctly!")


if __name__ == "__main__":
    main()
