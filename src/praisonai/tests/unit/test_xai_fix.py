#!/usr/bin/env python3
"""Test script to verify that xai/grok-4 works without OPENAI_API_KEY"""

import os


def test_xai_grok_without_openai_key():
    """Test that xai/grok-4 works without OPENAI_API_KEY set."""
    # Ensure OPENAI_API_KEY is not set to test the fix
    original_key = os.environ.pop('OPENAI_API_KEY', None)
    
    try:
        # Test the import that was failing
        from praisonaiagents import Agent
        
        # Test creating an agent with xai/grok-4
        agent = Agent(
            instructions="You are a PhD-level mathematician.",
            llm="xai/grok-4"
        )
        assert agent is not None
    finally:
        # Restore the key if it was set
        if original_key is not None:
            os.environ['OPENAI_API_KEY'] = original_key


if __name__ == "__main__":
    test_xai_grok_without_openai_key()
    print("\n✅ All tests passed! The issue has been fixed.")
    print("   You can now use litellm providers without setting OPENAI_API_KEY.")
