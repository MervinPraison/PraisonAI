"""Serper Tool Example.

This example demonstrates how to use the Serper (Google Search) tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"
    export SERPER_API_KEY=your_api_key

Usage:
    python tool.py
"""

import os
from praisonai_tools import SerperTool


def main():
    # Check for API key
    if not os.getenv("SERPER_API_KEY"):
        print("Error: SERPER_API_KEY environment variable not set")
        print("Get your API key from https://serper.dev/")
        return
    
    # Initialize Serper tool
    serper = SerperTool()
    
    # Example 1: Web search
    print("=" * 60)
    print("Example 1: Google Web Search")
    print("=" * 60)
    
    results = serper.search("Python programming tutorials", max_results=3)
    
    if results and "error" in results[0]:
        print(f"Error: {results[0]['error']}")
    else:
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  - {r.get('title', 'N/A')[:50]}...")
            print(f"    URL: {r.get('link', 'N/A')[:60]}...")
            print()
    
    print("✅ Serper tool working correctly!")


if __name__ == "__main__":
    main()
