"""Tavily Search Tool Example.

This example demonstrates how to use the Tavily search tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"
    export TAVILY_API_KEY=your_api_key

Usage:
    python tool.py
"""

import os
from praisonai_tools import TavilyTool

def main():
    # Check for API key
    if not os.getenv("TAVILY_API_KEY"):
        print("Error: TAVILY_API_KEY environment variable not set")
        print("Get your API key from https://tavily.com/")
        return
    
    # Initialize Tavily tool
    tavily = TavilyTool()
    
    # Example 1: Basic search
    print("=" * 60)
    print("Example 1: Basic Search")
    print("=" * 60)
    
    results = tavily.search("What is quantum computing?", max_results=3)
    
    if "error" in results:
        print(f"Error: {results['error']}")
    else:
        print(f"Query: {results.get('query')}")
        if "answer" in results:
            print(f"\nAI Answer: {results['answer'][:200]}...")
        print(f"\nResults ({len(results.get('results', []))}):")
        for r in results.get("results", []):
            print(f"  - {r['title']}")
            print(f"    URL: {r['url']}")
            print(f"    Score: {r.get('score', 'N/A')}")
    
    # Example 2: Search context for RAG
    print("\n" + "=" * 60)
    print("Example 2: Search Context (for RAG)")
    print("=" * 60)
    
    context = tavily.search_context("Python best practices 2024")
    print(f"Context (first 300 chars): {context[:300]}...")
    
    print("\n✅ Tavily tool working correctly!")


if __name__ == "__main__":
    main()
