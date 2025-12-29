#!/usr/bin/env python3
"""
AI Script Writer Example

Demonstrates generating scripts for different platforms.
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
sys.path.insert(0, '/Users/praison/Agent-Recipes/agent_recipes/templates/ai-script-writer')

from tools import write_youtube_script, write_short_script, write_thread


def main():
    print("=" * 60)
    print("AI Script Writer Example")
    print("=" * 60)
    
    topic = "AI agents are revolutionizing software development"
    
    # 1. YouTube Long-form Script
    print("\n1. Generating YouTube long-form script...")
    yt_script = write_youtube_script(
        topic=topic,
        target_length=180,
        key_points=["automation", "productivity", "future of coding"]
    )
    print(f"   Format: {yt_script.get('format')}")
    print(f"   Estimated duration: {yt_script.get('estimated_duration')}s")
    print(f"   Script preview:\n   {yt_script.get('script', '')[:200]}...")
    
    # 2. YouTube Short Script
    print("\n2. Generating YouTube Short script...")
    short_script = write_short_script(topic, duration=30)
    print(f"   Format: {short_script.get('format')}")
    print(f"   Script:\n   {short_script.get('script', '')[:300]}...")
    
    # 3. X Thread
    print("\n3. Generating X thread...")
    thread = write_thread(topic, num_tweets=3)
    print(f"   Thread ({len(thread.get('tweets', []))} tweets):")
    for i, tweet in enumerate(thread.get('tweets', [])[:3], 1):
        print(f"   Tweet {i}: {tweet[:80]}...")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
