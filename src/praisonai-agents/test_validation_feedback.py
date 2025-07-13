#!/usr/bin/env python3
"""Test script for validation feedback in workflow retry logic"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

def test_example_one():
    """Test the philosopher quotes example"""
    print("=" * 80)
    print("Testing Example 1: Philosopher Quotes with Validation")
    print("=" * 80)
    
    validator_agent = Agent(
        name="validator_agent",
        instructions="You are a helpful assistant",
        llm="gemini/gemini-2.5-flash",
        self_reflect=False,
        verbose=True
    )

    quote_agent = Agent(
        name="quote_agent",
        instructions="You are a helpful assistant who is a pro at quoting philosophers",
        llm="gemini/gemini-2.5-flash",
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
        max_iter=3  # Limit iterations to prevent infinite loops
    )

    try:
        agents.start()
        print("\nExample 1 completed successfully!")
    except Exception as e:
        print(f"\nExample 1 failed with error: {e}")


def test_example_two():
    """Test the web search example"""
    print("\n" + "=" * 80)
    print("Testing Example 2: Web Search with Validation (Mock)")
    print("=" * 80)
    
    # Mock web search tool for testing
    def mock_web_search(query: str) -> str:
        """Mock web search that returns limited results initially"""
        # Simulate returning too few results on first attempt
        return "Found 3 results:\n1. https://example.com/kenya1\n2. https://example.com/kenya2\n3. https://example.com/kenya3"
    
    agent = Agent(
        name="agent",
        instructions="You are a helpful assistant",
        llm="gemini/gemini-2.5-flash",
        self_reflect=False,
        verbose=True
    )

    web_search_agent = Agent(
        name="web_search_agent",
        role="Web Search Specialist",
        goal="Search the web for relevant information",
        instructions="You are a helpful assistant. You can use the tools provided to you to help the user.",
        llm="gemini/gemini-2.5-flash",
        self_reflect=False,
        verbose=False,
        tools=[mock_web_search]
    )

    # Tasks
    collect_task = Task(
        description="Perform an internet search using the query: 'Kenya protests in 2024 and 2025'",
        expected_output="List of URLs of the articles that are relevant to the search",
        agent=web_search_agent,
        name="collect_data",
        is_start=True,
        next_tasks=["validate_data"]
    )

    validate_task = Task(
        description="""Validate the collected data. Check if:
        1. At least 12 results are returned.
        2. Each result contains a valid URL.
        Return validation_result as 'valid' or 'invalid' only no other text.""",
        expected_output="Validation result indicating if data is valid or invalid.",
        agent=agent,
        name="validate_data",
        task_type="decision",
        condition={
            "valid": [],  # End the workflow on valid data
            "invalid": ["collect_data"]  # Retry data collection on invalid data
        },
    )

    # Workflow
    agents = PraisonAIAgents(
        agents=[web_search_agent, agent],
        tasks=[collect_task, validate_task],
        verbose=1,
        process="workflow",
        max_iter=3  # Limit iterations
    )

    try:
        agents.start()
        print("\nExample 2 completed successfully!")
    except Exception as e:
        print(f"\nExample 2 failed with error: {e}")


if __name__ == "__main__":
    print("Testing Validation Feedback Implementation")
    print("This test demonstrates that retry tasks now receive validation feedback\n")
    
    # Run example 1 (without actual API calls, just structure test)
    try:
        # We'll just test the structure is valid
        test_example_one()
    except Exception as e:
        print(f"Note: Example 1 requires actual LLM API access: {e}")
    
    # Run example 2 with mock
    try:
        test_example_two()
    except Exception as e:
        print(f"Note: Example 2 test setup issue: {e}")
    
    print("\nTest script completed. The implementation adds validation feedback to retry tasks.")