"""Exa Search Tool Example.

This example demonstrates how to use the Exa search tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"
    export EXA_API_KEY=your_api_key

Usage:
    python tool.py
"""

import os
from praisonai_tools import ExaTool


def main():
    # Check for API key
    if not os.getenv("EXA_API_KEY"):
        print("Error: EXA_API_KEY environment variable not set")
        print("Get your API key from https://exa.ai/")
        return
    
    # Initialize Exa tool
    exa = ExaTool()
    
    # Example 1: Neural search
    print("=" * 60)
    print("Example 1: Neural Search")
    print("=" * 60)
    
    results = exa.search("best practices for Python development", num_results=3)
    
    if results and "error" in results[0]:
        print(f"Error: {results[0]['error']}")
    else:
        print(f"Found {len(results)} results:")
        for r in results:
            print(f"  - {r.get('title', 'N/A')[:50]}...")
            print(f"    URL: {r.get('url', 'N/A')[:60]}...")
            print(f"    Score: {r.get('score', 'N/A')}")
            print()
    
    print("✅ Exa tool working correctly!")


if __name__ == "__main__":
    main()
