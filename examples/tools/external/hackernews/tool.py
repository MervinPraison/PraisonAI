"""Hacker News Tool Example.

This example demonstrates how to use the Hacker News tool with PraisonAI agents.

Requirements:
    pip install "praisonai[tools]"

Usage:
    python tool.py

Note: No API key required!
"""

from praisonai_tools import HackerNewsTool


def main():
    # Initialize Hacker News tool
    hn = HackerNewsTool()
    
    # Example 1: Get top stories
    print("=" * 60)
    print("Example 1: Top Stories")
    print("=" * 60)
    
    stories = hn.get_top_stories(limit=5)
    
    if stories and "error" in stories[0]:
        print(f"Error: {stories[0]['error']}")
    else:
        print(f"Found {len(stories)} top stories:")
        for story in stories:
            title = story.get("title") or "N/A"
            url = story.get("url") or "N/A"
            print(f"  - {title[:50]}...")
            print(f"    Score: {story.get('score', 'N/A')} | Comments: {story.get('descendants', 'N/A')}")
            print(f"    URL: {url[:60]}...")
            print()
    
    print("✅ Hacker News tool working correctly!")


if __name__ == "__main__":
    main()
