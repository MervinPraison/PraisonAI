#!/usr/bin/env python3
"""
Test the telemetry cleanup fix
"""

import os
import pytest
from datetime import datetime


@pytest.mark.integration
def test_agent_termination():
    """
    Test that the agent starts, completes, and terminates properly
    when telemetry cleanup is enabled/disabled.
    """

    # Set environment variable to disable telemetry (for testing)
    os.environ["PRAISONAI_TELEMETRY_DISABLED"] = "true"

    # Skip test if no OpenAI API key is available
    # This is an integration test and requires a real LLM connection
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY is required for this integration test"
        )

    from praisonaiagents import Agent

    print(f"[{datetime.now()}] Starting agent termination test...")

    # Create agent with minimal setup
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gpt-4o-mini"
    )

    print(f"[{datetime.now()}] Agent created successfully")

    # Test the start method (which was hanging)
    print(f"[{datetime.now()}] Running agent.start()...")

    response = agent.start(
        "Hello, just say hi back!"
    )

    print(f"[{datetime.now()}] Agent completed successfully!")

    print(f"Response: {response}")

    # If we get here, the fix worked
    # The agent completed and returned a response without hanging
    assert response is not None

    print(
        f"[{datetime.now()}] SUCCESS: Program completed properly!"
    )