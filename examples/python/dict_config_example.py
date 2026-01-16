#!/usr/bin/env python3
"""
Dict Config Example - Demonstrates dict shorthand for consolidated parameters.

This example shows how to use dict shorthand instead of importing config classes.
Dict input is strictly validated - unknown keys raise helpful errors.

Requirements:
- Set OPENAI_API_KEY environment variable
"""

import os


def example_dict_output_config():
    """Example: Using dict for output configuration."""
    from praisonaiagents import Agent
    
    # Dict shorthand - equivalent to OutputConfig(output="verbose", stream=False)
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
        output={"verbose": True, "stream": False},
    )
    
    result = agent.start("Say hello in one word.")
    print(f"Result: {result}")
    return agent


def example_dict_execution_config():
    """Example: Using dict for execution configuration."""
    from praisonaiagents import Agent
    
    # Dict shorthand for execution settings
    agent = Agent(
        name="FastAgent",
        instructions="You are a fast responder.",
        execution={"max_iter": 5, "timeout": 30},
    )
    
    result = agent.start("What is 2+2?")
    print(f"Result: {result}")
    return agent


def example_dict_validation_error():
    """Example: Dict with unknown key raises helpful error."""
    from praisonaiagents import Agent
    
    print("\n--- Testing dict validation error ---")
    try:
        # This will raise TypeError with helpful message
        Agent(
            name="Test",
            instructions="Test agent",
            output={"verbose": True, "invalid_key": "value"},
        )
    except TypeError as e:
        print(f"Expected error caught: {e}")
        # Shows: Unknown keys for output: ['invalid_key']. Valid keys: ...


def example_array_preset_override():
    """Example: Array [preset, {overrides}] pattern still works."""
    from praisonaiagents import Agent
    
    # Array pattern: preset name + override dict
    agent = Agent(
        name="VerboseAgent",
        instructions="You are verbose.",
        output=["verbose", {"stream": False}],
    )
    
    result = agent.start("Say hi.")
    print(f"Result: {result}")
    return agent


def example_base_url_api_key_separate():
    """Example: base_url and api_key remain separate parameters."""
    from praisonaiagents import Agent
    
    # base_url and api_key are NOT consolidated - they stay separate
    # This is intentional for security and clarity
    agent = Agent(
        name="CustomEndpoint",
        instructions="You use a custom endpoint.",
        llm="gpt-4o-mini",
        # base_url="http://localhost:11434/v1",  # Uncomment for Ollama
        # api_key=os.getenv("CUSTOM_API_KEY"),   # Separate parameter
    )
    
    return agent


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Some examples may fail.")
    
    print("=== Dict Config Examples ===\n")
    
    # Run validation error example (doesn't need API key)
    example_dict_validation_error()
    
    # Run examples that need API key
    if os.getenv("OPENAI_API_KEY"):
        print("\n--- Dict output config ---")
        example_dict_output_config()
        
        print("\n--- Array preset override ---")
        example_array_preset_override()
    else:
        print("\nSkipping API examples (no OPENAI_API_KEY)")
    
    print("\n=== Examples Complete ===")
