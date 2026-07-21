#!/usr/bin/env python3
"""
Test script to verify the termination fix works
"""

import sys
import os
import signal
import time
from threading import Timer

import pytest


# Add the src directory to the path so we can import praisonaiagents
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents')
)


# Set up timeout mechanism
def timeout_handler(signum, frame):
    print("ERROR: Test timed out - program is still hanging!")
    pytest.fail("Test timed out - program is still hanging!")


def test_agent_termination_fix():

    # Skip this integration test when no API key is available
    # The agent requires an LLM provider to execute successfully
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY is required for this integration test"
        )


    # Set up signal handler for timeout
    # SIGALRM and signal.alarm are only available on Unix systems
    # Windows does not support these APIs, so we check before using them
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, timeout_handler)

    if hasattr(signal, "alarm"):
        signal.alarm(30)


    try:
        # Import here to avoid issues with path setup
        from praisonaiagents import Agent


        print("Testing agent termination fix...")


        # Create agent with minimal setup
        agent = Agent(
            instructions="You are a helpful AI assistant"
        )


        # Run the same test as in the issue
        print("Running agent.start() ...")

        response = agent.start(
            "Write a short hello world message"
        )


        # Verify the agent completed successfully
        assert response is not None


        print("Agent completed successfully!")
        print(f"Response (truncated): {str(response)[:100]}...")


        # If we get here, the fix worked
        print("SUCCESS: Program terminated properly without hanging!")


    except Exception as e:
        # Convert unexpected errors into pytest failures
        # instead of exiting the test process directly
        print(f"ERROR: Exception occurred: {e}")

        import traceback
        traceback.print_exc()

        pytest.fail(
            f"Agent execution failed: {e}"
        )


    finally:
        # Cancel the alarm (Unix only)
        # Windows does not have signal.alarm()
        if hasattr(signal, "alarm"):
            signal.alarm(0)