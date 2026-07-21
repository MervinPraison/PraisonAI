#!/usr/bin/env python3
"""
Test script to verify the termination fix works
"""

import sys
import os
import _thread
from threading import Timer

import pytest


# Add the directory containing the praisonaiagents package to sys.path
sys.path.insert(
    0,
    os.path.abspath(os.path.dirname(__file__))
)


def test_agent_termination_fix():

    # Skip this integration test when no API key is available
    # The agent requires an LLM provider to execute successfully
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY is required for this integration test"
        )

    # Set up a cross-platform timeout using threading.Timer.
    # signal.alarm/SIGALRM are Unix-only, so we use Timer +
    # _thread.interrupt_main() to work on both Windows and Unix
    # without abruptly terminating the pytest process.
    timed_out = {"value": False}

    def timeout_trigger():
        timed_out["value"] = True
        print("ERROR: Test timed out - program is still hanging!")
        _thread.interrupt_main()

    timer = Timer(30.0, timeout_trigger)
    timer.start()

    try:
        # Import here to avoid issues with path setup
        from praisonaiagents import Agent

        print("Testing agent termination fix...")

        # Create agent with minimal setup using a context manager
        # so resources are cleaned up when the test completes or fails
        with Agent(instructions="You are a helpful AI assistant") as agent:
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

    except KeyboardInterrupt:
        # Raised by _thread.interrupt_main() when the timeout fires
        pytest.fail("Test timed out - program is still hanging!")

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
        # Always cancel the timer so it cannot fire after completion
        timer.cancel()
