#!/usr/bin/env python3
"""
Test real streaming behavior for different configurations.
This script tests that streaming works correctly with various settings.
"""

import os
import sys
from praisonaiagents import Agent

def test_real_streaming():
    """Test real streaming behavior with different configurations."""
    
    # Test configurations
    test_cases = [
        {
            "name": "Stream True + Verbose True",
            "stream": True,
            "verbose": True,
            "expected": "Real-time streaming with progressive content display"
        },
        {
            "name": "Stream True + Verbose False", 
            "stream": True,
            "verbose": False,
            "expected": "Real-time streaming but no display (callbacks only)"
        },
        {
            "name": "Stream False + Verbose True",
            "stream": False,
            "verbose": True,
            "expected": "'Generating response...' animation with elapsed time, no content"
        },
        {
            "name": "Stream False + Verbose False",
            "stream": False,
            "verbose": False,
            "expected": "No display at all, just returns response"
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"Testing: {test_case['name']}")
        print(f"Configuration: stream={test_case['stream']}, verbose={test_case['verbose']}")
        print(f"Expected: {test_case['expected']}")
        print(f"{'='*60}\n")
        
        try:
            # Create agent with specific configuration
            agent = Agent(
                name="Test Agent",
                role="Testing Assistant",
                goal="Test streaming behavior",
                backstory="I am a test agent for verifying streaming functionality.",
                llm="gpt-4o-mini",  # You can change this to test other providers
                stream=test_case["stream"],
                verbose=test_case["verbose"]
            )
            
            # Test the agent
            prompt = "Count from 1 to 10 slowly, with each number on a new line."
            print(f"Sending prompt: {prompt}\n")
            
            response = agent.chat(prompt)
            
            if not test_case["verbose"]:
                # If verbose is False, we need to print the response manually
                print(f"\nResponse:\n{response}")
            
            print(f"\n{'='*60}")
            print(f"Test completed!")
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            continue
        
        # Wait for user to observe the behavior
        input("\nPress Enter to continue to the next test...")
    
    # Test with different providers
    print("\n\nTesting with different providers...")
    providers = [
        ("Gemini", "gemini/gemini-1.5-flash"),
        ("Anthropic", "claude-3-haiku-20240307"),
        # Add more providers as needed
    ]
    
    for name, model in providers:
        print(f"\n{'='*60}")
        print(f"Testing real streaming with {name}")
        print(f"Configuration: stream=True, verbose=True")
        print(f"{'='*60}\n")
        
        try:
            agent = Agent(
                name=f"{name} Agent",
                role="Testing Assistant", 
                goal="Test streaming",
                backstory=f"Testing {name} streaming",
                llm=model,
                stream=True,
                verbose=True
            )
            
            response = agent.chat("Write a haiku about streaming data.")
            print(f"\nTest with {name} completed!")
            
        except Exception as e:
            print(f"\nError testing with {name}: {str(e)}")
            if "API" in str(e) or "key" in str(e).lower():
                print(f"Make sure you have the required API key set for {name}")

if __name__ == "__main__":
    print("Starting real streaming behavior tests...")
    print("This test verifies the correct behavior for all combinations of stream and verbose settings.\n")
    
    # Check for API keys
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. OpenAI tests will fail.")
    
    test_real_streaming()
    
    print("\n\nAll tests completed!")
    print("\nSummary of expected behaviors:")
    print("- stream=True, verbose=True: Real-time streaming with content display")
    print("- stream=True, verbose=False: Real-time streaming, no display")  
    print("- stream=False, verbose=True: 'Generating...' animation, no content")
    print("- stream=False, verbose=False: No display at all")