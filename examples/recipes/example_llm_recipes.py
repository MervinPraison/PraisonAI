#!/usr/bin/env python3
"""
Example: LLM-based Recipes

Demonstrates usage of LLM-powered recipes:
- ai-blog-generator
- ai-social-media-generator
- ai-faq-generator
- ai-sentiment-analyzer
"""

import os
import sys

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    sys.exit(1)

# Add recipe tools to path
sys.path.insert(0, "/Users/praison/PraisonAI-tools/praisonai_tools/recipe_tools")

from llm_tool import LLMTool, llm_complete


def example_blog_generator():
    """Generate a blog post."""
    print("\n=== AI Blog Generator ===")
    
    llm = LLMTool(provider="openai", model="gpt-4o-mini")
    
    topic = "The Future of AI in Healthcare"
    
    response = llm.complete(
        f"""Write a short blog post (3 paragraphs) about: {topic}
        
Include:
- Engaging introduction
- Key points
- Call to action

Format as markdown.""",
        system="You are an expert blog writer specializing in technology topics.",
        max_tokens=500,
    )
    
    print(f"Topic: {topic}")
    print(f"\nGenerated Blog Post:\n{response.content}")
    print(f"\nTokens used: {response.usage.get('total_tokens', 'N/A')}")


def example_social_media_generator():
    """Generate social media posts."""
    print("\n=== AI Social Media Generator ===")
    
    llm = LLMTool(provider="openai", model="gpt-4o-mini")
    
    content = "We just launched our new AI-powered productivity app!"
    
    response = llm.complete(
        f"""Create social media posts for the following announcement:
{content}

Generate posts for:
1. Twitter (280 chars max)
2. LinkedIn (professional tone)
3. Instagram (with emoji suggestions)

Format each clearly.""",
        system="You are a social media marketing expert.",
        max_tokens=400,
    )
    
    print(f"Content: {content}")
    print(f"\nGenerated Posts:\n{response.content}")


def example_faq_generator():
    """Generate FAQ from content."""
    print("\n=== AI FAQ Generator ===")
    
    llm = LLMTool(provider="openai", model="gpt-4o-mini")
    
    documentation = """
    Our product is a cloud-based project management tool.
    It supports team collaboration, task tracking, and reporting.
    Pricing starts at $10/month per user.
    We offer a 14-day free trial.
    Integration with Slack, GitHub, and Jira is available.
    """
    
    response = llm.complete(
        f"""Based on this documentation, generate 5 FAQ questions and answers:

{documentation}

Format as:
Q: [question]
A: [answer]
""",
        system="You are a technical writer creating FAQ documentation.",
        max_tokens=400,
    )
    
    print(f"Generated FAQ:\n{response.content}")


def example_sentiment_analyzer():
    """Analyze sentiment in text."""
    print("\n=== AI Sentiment Analyzer ===")
    
    llm = LLMTool(provider="openai", model="gpt-4o-mini")
    
    reviews = [
        "This product is amazing! Best purchase ever.",
        "Terrible experience. Would not recommend.",
        "It's okay, nothing special but does the job.",
    ]
    
    for review in reviews:
        response = llm.complete(
            f"""Analyze the sentiment of this text and respond with ONLY one word: POSITIVE, NEGATIVE, or NEUTRAL

Text: {review}""",
            max_tokens=10,
        )
        print(f"Review: {review[:50]}...")
        print(f"Sentiment: {response.content.strip()}\n")


if __name__ == "__main__":
    print("=" * 60)
    print("LLM-Based Recipes Examples")
    print("=" * 60)
    
    example_blog_generator()
    example_social_media_generator()
    example_faq_generator()
    example_sentiment_analyzer()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
