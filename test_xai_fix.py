#!/usr/bin/env python3
"""Test script to verify that xai/grok-4 works without OPENAI_API_KEY"""

import os
import sys

# Ensure OPENAI_API_KEY is not set to test the fix
if 'OPENAI_API_KEY' in os.environ:
    del os.environ['OPENAI_API_KEY']

# Test the import that was failing
try:
    from praisonaiagents import Agent
    print("✅ Successfully imported praisonaiagents without OPENAI_API_KEY!")
except ValueError as e:
    print(f"❌ Import failed with error: {e}")
    sys.exit(1)

# Test creating an agent with xai/grok-4
try:
    agent = Agent(
        instructions="You are a PhD-level mathematician.",
        llm="xai/grok-4"
    )
    print("✅ Successfully created Agent with xai/grok-4!")
    print(f"   Agent using LLM: {agent.llm}")
except Exception as e:
    print(f"❌ Failed to create agent: {e}")
    sys.exit(1)

print("\n✅ All tests passed! The issue has been fixed.")
print("   You can now use litellm providers without setting OPENAI_API_KEY.")