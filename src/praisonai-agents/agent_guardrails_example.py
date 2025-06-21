#!/usr/bin/env python3
"""
Agent-level guardrails example.

This example demonstrates how to use guardrails at the Agent level,
which will apply to all tasks executed by that agent.
"""

from typing import Tuple, Any
from praisonaiagents import Agent, TaskOutput

def validate_content_length(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validate that task output content meets minimum length requirement.
    
    Args:
        task_output: The task output to validate
        
    Returns:
        Tuple of (success, result_or_error_message)
    """
    if len(task_output.raw) < 50:
        return False, "Content too short - must be at least 50 characters"
    return True, task_output

def validate_professional_tone(task_output: TaskOutput) -> Tuple[bool, Any]:
    """
    Validate that the content has a professional tone.
    
    Args:
        task_output: The task output to validate
        
    Returns:
        Tuple of (success, result_or_error_message)
    """
    content = task_output.raw.lower()
    unprofessional_words = ['yo', 'dude', 'awesome', 'cool', 'lol']
    
    for word in unprofessional_words:
        if word in content:
            return False, f"Content contains unprofessional word: '{word}'"
    
    return True, task_output

def main():
    """Demonstrate Agent-level guardrails with function-based and LLM-based validation."""
    
    print("=== Agent Guardrail Examples ===\n")
    
    # Example 1: Function-based guardrail
    print("1. Function-based guardrail (content length validation):")
    agent1 = Agent(
        name="ContentWriter",
        instructions="You are a professional content writer who creates detailed responses",
        guardrail=validate_content_length,
        max_guardrail_retries=2
    )
    
    try:
        result1 = agent1.start("Write a brief welcome message")
        print(f"Result: {result1}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    # Example 2: LLM-based guardrail (string description)
    print("2. LLM-based guardrail (professional tone validation):")
    agent2 = Agent(
        name="BusinessWriter", 
        instructions="You are a business communication expert",
        guardrail="Ensure the content is professional, formal, and suitable for business communication. No casual language or slang.",
        max_guardrail_retries=3
    )
    
    try:
        result2 = agent2.start("Write a welcome message for new employees")
        print(f"Result: {result2}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    # Example 3: Multiple agents with different guardrails
    print("3. Professional tone function-based guardrail:")
    agent3 = Agent(
        name="ProfessionalWriter",
        instructions="Write professional business content",
        guardrail=validate_professional_tone,
        max_guardrail_retries=2
    )
    
    try:
        result3 = agent3.start("Write a casual greeting message")
        print(f"Result: {result3}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    print("=== Agent Guardrails Demonstration Complete ===")

if __name__ == "__main__":
    main()
