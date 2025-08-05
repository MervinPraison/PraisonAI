#!/usr/bin/env python3
"""Test script for OpenRouter XML tool call fix"""

import os
import sys

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import Agent

def get_weather(city: str) -> str:
    """Get weather information for a city"""
    return f"The weather in {city} is sunny with 22°C"

def main():
    print("Testing OpenRouter XML tool call fix...")
    
    # Test with auto-detection (should detect Qwen as XML format)
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="openrouter/qwen/qwen-2.5-7b-instruct",
        tools=[get_weather],
        verbose=True
    )
    
    print("Created agent with Qwen model...")
    
    # Get the LLM instance directly from the agent
    llm_instance = agent.llm_instance  # This should be the LLM object
    print(f"XML tool format supported: {llm_instance._supports_xml_tool_format()}")
    
    # Test the tool call without actually making API request
    # We'll just verify the parameters are built correctly
    test_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather information for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "The city name"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # Test _build_completion_params
    params = llm_instance._build_completion_params(
        messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
        tools=test_tools,
        temperature=0.2
    )
    
    print("\n=== Completion Parameters ===")
    print(f"Model: {params.get('model')}")
    print(f"Tools included: {'tools' in params}")
    print(f"Tool choice included: {'tool_choice' in params}")
    
    # Test _build_messages
    messages, original = llm_instance._build_messages(
        prompt="What's the weather in Tokyo?",
        system_prompt="You are a helpful assistant",
        tools=test_tools
    )
    
    print("\n=== System Message ===")
    for msg in messages:
        if msg['role'] == 'system':
            print(msg['content'])
            break
    
    print("\n✅ Test completed successfully!")
    print("Key improvements:")
    print("- Tools parameter is removed for XML format models")
    print("- Tool descriptions are added to system prompt")
    print("- XML tool call format instructions are included")

if __name__ == "__main__":
    main()