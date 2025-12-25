"""ArXiv Tool Example.

This example demonstrates how to use the ArXiv tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: No API key required!
"""

from praisonai_tools import ArxivTool


def main():
    # Initialize ArXiv tool (no API key needed)
    arxiv = ArxivTool()
    
    # Example 1: Search ArXiv
    print("=" * 60)
    print("Example 1: Search ArXiv")
    print("=" * 60)
    
    results = arxiv.search("transformer neural networks", max_results=3)
    
    if results and "error" in results[0]:
        print(f"Error: {results[0]['error']}")
    else:
        print(f"Found {len(results)} papers:")
        for paper in results:
            print(f"\n  Title: {paper.get('title', 'N/A')[:60]}...")
            authors = paper.get('authors', [])
            if authors:
                print(f"  Authors: {', '.join(authors[:2])}...")
            print(f"  Published: {paper.get('published', 'N/A')}")
            print(f"  PDF: {paper.get('pdf_url', 'N/A')}")
    
    print("\n✅ ArXiv tool working correctly!")


if __name__ == "__main__":
    main()
