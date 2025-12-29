#!/usr/bin/env python3
"""
AI Hook Generator Example

Demonstrates generating attention-grabbing hooks.
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
sys.path.insert(0, '/Users/praison/Agent-Recipes/agent_recipes/templates/ai-hook-generator')

from tools import generate_hooks, rank_hooks


def main():
    print("=" * 60)
    print("AI Hook Generator Example")
    print("=" * 60)
    
    topic = "GPT-5 just released with groundbreaking capabilities"
    
    # 1. Generate hooks
    print(f"\n1. Generating hooks for: '{topic}'")
    hooks = generate_hooks(topic, num_variants=5)
    print(f"   Generated {len(hooks.get('hooks', []))} hooks:")
    
    for hook in hooks.get('hooks', []):
        print(f"\n   [{hook.get('style', 'unknown')}]")
        print(f"   {hook.get('text', '')}")
    
    # 2. Rank hooks
    print("\n2. Ranking hooks by engagement potential...")
    ranked = rank_hooks(hooks.get('hooks', []))
    best = ranked.get('best_hook', {})
    print(f"\n   Best hook (score: {best.get('score', 0)}):")
    print(f"   {best.get('text', '')}")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
