#!/usr/bin/env python3
"""Test script to verify validation feedback in workflow retry logic"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

def test_quote_example():
    """Test the Aristotle quote example (randomized output - should work)"""
    print("\n=== Testing Quote Example (Randomized Output) ===")
    
    validator_agent = Agent(
        name="validator_agent",
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=True
    )

    quote_agent = Agent(
        name="quote_agent",
        instructions="You are a helpful assistant who is a pro at quoting philosophers",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=False
    )

    collect_task = Task(
        description="Quote Aristotle",
        expected_output="List of Quotes from Aristotle",
        agent=quote_agent,
        name="collect_data",
        is_start=True,
        next_tasks=["validate_data"]
    )

    validate_task = Task(
        description="""Validate the collected data. Check if:
        1. At least 25 results are returned.
        2. Each is a quote from Aristotle.
        Return validation_result as 'valid' or 'invalid' only no other text.""",
        expected_output="Validation result indicating if data is valid or invalid.",
        agent=validator_agent,
        name="validate_data",
        task_type="decision",
        condition={
            "valid": [],  # End the workflow on valid data
            "invalid": ["collect_data"]  # Retry data collection on invalid data
        },
    )

    # Workflow
    agents = PraisonAIAgents(
        agents=[quote_agent, validator_agent],
        tasks=[collect_task, validate_task],
        verbose=1,
        process="workflow",
        max_iter=3  # Limit iterations for testing
    )

    print("Starting workflow...")
    result = agents.start()
    print(f"Workflow completed. Result: {result}")
    
    # Check if validation feedback was passed
    if hasattr(collect_task, 'validation_feedback'):
        print(f"Validation feedback found: {collect_task.validation_feedback}")
    else:
        print("No validation feedback found on collect_task")

def test_simple_feedback():
    """Simple test to verify feedback mechanism"""
    print("\n=== Testing Simple Feedback Mechanism ===")
    
    agent = Agent(
        name="test_agent",
        instructions="You are a helpful assistant. When you receive validation feedback, acknowledge it in your response.",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=True
    )

    collect_task = Task(
        description="Generate a list of exactly 5 items",
        expected_output="A list with exactly 5 items",
        agent=agent,
        name="collect_data",
        is_start=True,
        next_tasks=["validate_data"]
    )

    validate_task = Task(
        description="""Check if the list has exactly 5 items. 
        If it has 5 items, return 'valid'.
        If not, return 'invalid' and explain what's wrong.""",
        expected_output="Validation result",
        agent=agent,
        name="validate_data",
        task_type="decision",
        condition={
            "valid": [],
            "invalid": ["collect_data"]
        },
    )

    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[collect_task, validate_task],
        verbose=2,
        process="workflow",
        max_iter=3
    )

    result = agents.start()
    print(f"Workflow result: {result}")

if __name__ == "__main__":
    print("Testing Validation Feedback Implementation")
    print("=" * 50)
    
    # Run simple test first
    test_simple_feedback()
    
    # Then run the quote example
    # test_quote_example()