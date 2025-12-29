#!/usr/bin/env python3
"""
AI Brief Generator Example

Demonstrates generating news briefs from articles.
Requires: OPENAI_API_KEY
"""

import os
import sys

# Check for API key
if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY environment variable required")
    print("Set it with: export OPENAI_API_KEY=your_key")
    sys.exit(1)

# Add the Agent-Recipes templates to path
sys.path.insert(0, '/Users/praison/Agent-Recipes/agent_recipes/templates/ai-brief-generator')

from tools import generate_brief, extract_highlights


def main():
    print("=" * 60)
    print("AI Brief Generator Example")
    print("=" * 60)
    
    # Sample articles
    articles = [
        {
            "title": "OpenAI Releases GPT-5 with Multimodal Capabilities",
            "content": "OpenAI announced GPT-5 today with major improvements in reasoning, multimodal understanding, and reduced hallucinations.",
            "source": "TechCrunch",
            "url": "https://example.com/gpt5"
        },
        {
            "title": "Google Gemini 2.0 Launches with Real-time Video Understanding",
            "content": "Google unveiled Gemini 2.0 with breakthrough capabilities in real-time video analysis and native tool use.",
            "source": "The Verge",
            "url": "https://example.com/gemini2"
        },
        {
            "title": "Anthropic Claude 4 Sets New Benchmarks",
            "content": "Anthropic's Claude 4 achieves state-of-the-art results on coding, math, and reasoning benchmarks.",
            "source": "Wired",
            "url": "https://example.com/claude4"
        }
    ]
    
    # 1. Generate daily brief
    print("\n1. Generating daily brief...")
    brief = generate_brief(articles, format="daily", max_articles=3)
    print(f"   Format: daily")
    print(f"   Articles included: {brief.get('article_count', 0)}")
    print(f"\n   Brief preview:\n   {brief.get('brief', '')[:500]}...")
    
    # 2. Extract highlights
    print("\n2. Extracting highlights...")
    highlights = extract_highlights(articles, num_highlights=3)
    print(f"   Highlights:")
    for h in highlights.get('highlights', []):
        print(f"   - {h}")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
