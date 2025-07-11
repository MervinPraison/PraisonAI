#!/usr/bin/env python3
"""Example demonstrating the validation feedback fix for workflow retry logic"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

def create_web_search_example():
    """Create the web search example that requires context for improvement"""
    
    # Mock web search tool for demonstration
    def mock_web_search(query: str) -> str:
        """Mock web search that returns few results initially"""
        # This simulates a search that doesn't return enough results
        # In real scenario, this would use actual web search
        return """Search Results:
1. Kenya protests 2024 - Wikipedia
   URL: https://en.wikipedia.org/wiki/2024_Kenya_protests
2. Kenya unrest: What's behind the protests? - BBC
   URL: https://www.bbc.com/news/kenya-protests-2024
3. Kenya protests continue into 2025 - Reuters
   URL: https://www.reuters.com/kenya-protests-2025"""

    agent = Agent(
        name="agent",
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=True
    )

    web_search_agent = Agent(
        name="web_search_agent",
        role="Web Search Specialist",
        goal="Search the web for relevant information",
        instructions="""You are a helpful assistant. When searching for information:
        1. If you receive validation feedback about insufficient results, expand your search approach
        2. Consider using different search queries or multiple searches
        3. Acknowledge any validation feedback in your response""",
        llm="gpt-4o-mini",
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
        
        If validation fails, provide specific feedback about what's wrong.
        Return validation_result as 'valid' or 'invalid'.""",
        expected_output="Validation result indicating if data is valid or invalid.",
        agent=agent,
        name="validate_data",
        task_type="decision",
        condition={
            "valid": [],  # End the workflow on valid data
            "invalid": ["collect_data"]  # Retry data collection on invalid data
        },
    )

    return web_search_agent, agent, collect_task, validate_task

def create_simple_example():
    """Create a simple example to demonstrate the feedback mechanism"""
    
    agent = Agent(
        name="generator_agent",
        instructions="""You are a helpful assistant that generates lists.
        When you receive validation feedback, acknowledge it and adjust your output accordingly.
        If told your list is too short, generate more items.
        If told your list is too long, generate fewer items.""",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=True
    )
    
    validator = Agent(
        name="validator_agent",
        instructions="You are a strict validator that checks if lists have exactly 10 items.",
        llm="gpt-4o-mini",
        self_reflect=False,
        verbose=True
    )

    generate_task = Task(
        description="Generate a list of 10 interesting facts about space",
        expected_output="A list with exactly 10 facts",
        agent=agent,
        name="generate_list",
        is_start=True,
        next_tasks=["validate_list"]
    )

    validate_task = Task(
        description="""Check if the list has exactly 10 items.
        If it has 10 items, return 'valid'.
        If it has fewer than 10 items, return 'invalid' and say 'The list has only X items, need 10'.
        If it has more than 10 items, return 'invalid' and say 'The list has X items, need exactly 10'.""",
        expected_output="Validation result with feedback",
        agent=validator,
        name="validate_list",
        task_type="decision",
        condition={
            "valid": [],
            "invalid": ["generate_list"]
        },
    )

    return agent, validator, generate_task, validate_task

def main():
    print("=" * 70)
    print("VALIDATION FEEDBACK DEMONSTRATION")
    print("=" * 70)
    
    # Test simple example
    print("\n### Example 1: Simple List Generation with Feedback")
    print("-" * 50)
    
    agent, validator, generate_task, validate_task = create_simple_example()
    
    agents = PraisonAIAgents(
        agents=[agent, validator],
        tasks=[generate_task, validate_task],
        verbose=1,
        process="workflow",
        max_iter=5  # Allow up to 5 iterations
    )
    
    print("Starting workflow with validation feedback...")
    result = agents.start()
    
    print("\n### Example 2: Web Search with Context-Dependent Retry")
    print("-" * 50)
    
    web_agent, val_agent, collect_task, val_task = create_web_search_example()
    
    agents2 = PraisonAIAgents(
        agents=[web_agent, val_agent],
        tasks=[collect_task, val_task],
        verbose=1,
        process="workflow",
        max_iter=5
    )
    
    print("Starting web search workflow...")
    result2 = agents2.start()
    
    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    
    print("\nKey Points Demonstrated:")
    print("1. When validation fails, the retry task receives feedback about why it failed")
    print("2. The agent can see the rejected output and validation reason")
    print("3. This allows context-dependent tasks to improve on retry")
    print("4. The solution is backward compatible - existing workflows continue to work")

if __name__ == "__main__":
    main()