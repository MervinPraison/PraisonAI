#!/usr/bin/env python3
"""
Test streaming behavior for different LLM providers.
This script tests the streaming functionality with OpenAI, LiteLLM, and Gemini models.
"""

import os
import sys
from praisonaiagents import Agent

def test_streaming_behavior():
    """Test streaming behavior with different configurations."""
    
    # Test configurations
    test_cases = [
        {
            "name": "OpenAI - Stream True",
            "llm": "gpt-5-nano",
            "stream": True,
            "verbose": True,
            "expected": "Should show real-time streaming"
        },
        {
            "name": "OpenAI - Stream False",
            "llm": "gpt-5-nano", 
            "stream": False,
            "verbose": True,
            "expected": "Should show 'Generating...' animation during API call"
        },
        {
            "name": "Gemini - Stream True",
            "llm": "gemini/gemini-1.5-flash",
            "stream": True,
            "verbose": True,
            "expected": "Should show real-time streaming"
        },
        {
            "name": "Gemini - Stream False",
            "llm": "gemini/gemini-1.5-flash",
            "stream": False,
            "verbose": True,
            "expected": "Should show 'Generating...' animation during API call"
        },
        {
            "name": "LiteLLM/Ollama - Stream True",
            "llm": "ollama/llama3.2",
            "stream": True,
            "verbose": True,
            "expected": "Should show real-time streaming (if Ollama is running)"
        },
        {
            "name": "LiteLLM/Ollama - Stream False",
            "llm": "ollama/llama3.2",
            "stream": False,
            "verbose": True,
            "expected": "Should show 'Generating...' animation during API call (if Ollama is running)"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {test_case['name']}")
        print(f"Expected: {test_case['expected']}")
        print(f"{'='*60}\n")
        
        try:
            # Create agent with specific configuration
            agent = Agent(
                name="Test Agent",
                role="Testing Assistant",
                goal="Test streaming behavior",
                backstory="I am a test agent for verifying streaming functionality.",
                llm=test_case["llm"],
                stream=test_case["stream"],
                verbose=test_case["verbose"]
            )
            
            # Test the agent
            response = agent.chat("Write a haiku about streaming data.")
            
            print(f"\nResponse received: {response[:100]}..." if len(response) > 100 else f"\nResponse received: {response}")
            print(f"\nTest completed successfully!")
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            if "ollama" in test_case["llm"].lower():
                print("Note: Ollama tests require Ollama to be running locally.")
            continue
        
        # Wait for user to observe the behavior
        input("\nPress Enter to continue to the next test...")

if __name__ == "__main__":
    print("Starting streaming behavior tests...")
    print("Make sure you have the required API keys set:")
    print("- OPENAI_API_KEY for OpenAI tests")
    print("- GEMINI_API_KEY or GOOGLE_API_KEY for Gemini tests")
    print("- Ollama running locally for Ollama tests\n")
    
    test_streaming_behavior()
    
    print("\n\nAll tests completed!")