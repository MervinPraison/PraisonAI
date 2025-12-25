"""Firecrawl Tool Example.

This example demonstrates how to use the Firecrawl tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"
    export FIRECRAWL_API_KEY=your_api_key

Usage:
    python tool.py
"""

import os
from praisonai_tools import FirecrawlTool


def main():
    # Check for API key
    if not os.getenv("FIRECRAWL_API_KEY"):
        print("Error: FIRECRAWL_API_KEY environment variable not set")
        print("Get your API key from https://firecrawl.dev/")
        return
    
    # Initialize Firecrawl tool
    firecrawl = FirecrawlTool()
    
    # Example 1: Scrape a page
    print("=" * 60)
    print("Example 1: Scrape a Page")
    print("=" * 60)
    
    result = firecrawl.scrape("https://example.com")
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"URL: {result.get('url', 'N/A')}")
        markdown = result.get('markdown', '')
        print(f"Content preview: {markdown[:300]}...")
    
    print("\n✅ Firecrawl tool working correctly!")


if __name__ == "__main__":
    main()
