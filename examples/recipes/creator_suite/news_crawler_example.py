#!/usr/bin/env python3
"""
AI News Crawler Example

Demonstrates crawling AI news from multiple sources.
"""

import os
import sys

# Add the Agent-Recipes templates to path
sys.path.insert(0, '/Users/praison/Agent-Recipes/agent_recipes/templates/ai-news-crawler')

from tools import crawl_hackernews, crawl_reddit_ai, crawl_arxiv, crawl_ai_news


def main():
    print("=" * 60)
    print("AI News Crawler Example")
    print("=" * 60)
    
    # 1. Crawl HackerNews (no API key needed)
    print("\n1. Crawling HackerNews...")
    hn_articles = crawl_hackernews(max_articles=5, time_window_hours=48)
    print(f"   Found {len(hn_articles)} articles from HackerNews")
    for article in hn_articles[:3]:
        print(f"   - {article.get('title', 'No title')[:60]}...")
    
    # 2. Crawl arXiv (no API key needed)
    print("\n2. Crawling arXiv...")
    arxiv_articles = crawl_arxiv(categories=["cs.AI", "cs.LG"], max_results=5)
    print(f"   Found {len(arxiv_articles)} articles from arXiv")
    for article in arxiv_articles[:3]:
        print(f"   - {article.get('title', 'No title')[:60]}...")
    
    # 3. Full crawl from multiple sources
    print("\n3. Full multi-source crawl...")
    all_articles = crawl_ai_news(
        sources=["hackernews", "arxiv"],
        max_articles=10,
        time_window_hours=48
    )
    print(f"   Total articles: {all_articles.get('total', 0)}")
    print(f"   Sources crawled: {all_articles.get('sources_crawled', [])}")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
