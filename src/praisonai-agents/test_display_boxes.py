#!/usr/bin/env python3
"""Test script to compare display output between OpenAI and Gemini models."""

import os
from praisonaiagents import Agent

def test_model_display(model_name, api_key_env=None):
    """Test display output for a specific model."""
    print(f"\n{'='*60}")
    print(f"Testing {model_name}")
    print('='*60)
    
    # Set API key if provided
    if api_key_env:
        if not os.getenv(api_key_env):
            print(f"Skipping {model_name} - {api_key_env} not set")
            return
    
    try:
        # Create agent with the specified model
        agent = Agent(
            name=f"{model_name.split('/')[-1]}_agent",
            role="Math Assistant",
            goal="Help with simple calculations",
            backstory="You are a helpful math assistant.",
            llm=model_name,
            verbose=True,  # This should trigger display_interaction
            markdown=True
        )
        
        # Simple test prompt
        response = agent.chat("What is 5 + 3? Please provide a brief answer.")
        
        print(f"\nRaw response: {response}")
        
    except Exception as e:
        print(f"Error with {model_name}: {e}")

# Test with different models
if __name__ == "__main__":
    print("Testing display output for different LLM models...")
    
    # Test OpenAI
    test_model_display("gpt-4o-mini", "OPENAI_API_KEY")
    
    # Test Gemini
    test_model_display("gemini/gemini-1.5-flash", "GEMINI_API_KEY")
    
    # Test Anthropic (if available)
    test_model_display("claude-3-haiku-20240307", "ANTHROPIC_API_KEY")
    
    print("\n\nTest completed!")