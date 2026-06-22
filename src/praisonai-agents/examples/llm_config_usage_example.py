#!/usr/bin/env python3
"""Example of using LLMConfig with Agent for model fallback configuration."""

from praisonaiagents import Agent
from praisonaiagents.config import LLMConfig

# Example 1: Pass LLMConfig via llm parameter
def example_llm_param():
    """Using LLMConfig via the llm parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant",
        llm=config  # Pass LLMConfig object directly
    )
    
    print(f"Primary model: {agent.llm}")
    print(f"Fallback models: {agent.fallback_models}")
    print(f"Base URL: {agent.base_url}")
    print(f"API Key: {agent.api_key}")

# Example 2: Pass LLMConfig via model parameter
def example_model_param():
    """Using LLMConfig via the model parameter (preferred)."""
    config = LLMConfig(
        model="gpt-4o", 
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant",
        model=config  # Pass LLMConfig via model parameter
    )
    
    print(f"Primary model: {agent.llm}")
    print(f"Fallback models: {agent.fallback_models}")
    print(f"Base URL: {agent.base_url}")
    print(f"API Key: {agent.api_key}")

# Example 3: Traditional usage still works
def example_traditional():
    """Traditional usage without LLMConfig (no fallback support)."""
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant",
        model="gpt-4o",
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    print(f"Primary model: {agent.llm}")
    print(f"Fallback models: {agent.fallback_models}")  # Will be empty
    print(f"Base URL: {agent.base_url}")
    print(f"API Key: {agent.api_key}")

if __name__ == "__main__":
    print("=== Example 1: LLMConfig via llm parameter ===")
    example_llm_param()
    print()
    
    print("=== Example 2: LLMConfig via model parameter ===")
    example_model_param()
    print()
    
    print("=== Example 3: Traditional usage (no fallback) ===")
    example_traditional()