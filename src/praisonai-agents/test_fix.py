#!/usr/bin/env python3
"""
Integration test verifying that Agent.start() terminates correctly.

This test ensures the agent does not hang during shutdown
(e.g. telemetry cleanup) and works across Windows, Linux,
and macOS.
"""

import os
import threading
import _thread
from datetime import datetime

import pytest


@pytest.mark.integration
def test_agent_termination():
    """
    Verify that Agent.start() returns without hanging.

    A cross-platform threading.Timer is used instead of
    signal.alarm(), since signal.alarm() is only available
    on Unix platforms.
    """

    # Disable telemetry so we're testing termination only.
    os.environ["PRAISONAI_TELEMETRY_DISABLED"] = "true"

    # Skip if no OpenAI API key is available.
    # (Keeping this simple for now to avoid adding provider
    # detection logic to this smoke test.)
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY is required for this integration test"
        )

    from praisonaiagents import Agent

    print(f"[{datetime.now()}] Starting agent termination test...")

    # Cross-platform timeout
    def timeout_handler():
        print("ERROR: Agent did not terminate within 30 seconds")
        _thread.interrupt_main()

    timer = threading.Timer(30.0, timeout_handler)
    timer.start()

    try:
        # Use a context manager so resources are always cleaned up.
        with Agent(
            instructions="You are a helpful AI assistant",
            llm="gpt-4o-mini",
        ) as agent:

            print(f"[{datetime.now()}] Agent created successfully")

            print(f"[{datetime.now()}] Running agent.start()...")

            response = agent.start(
                "Hello, just say hi back!"
            )

            print(f"[{datetime.now()}] Agent completed successfully!")
            print(f"Response: {response}")

            # The purpose of this test is to verify that execution
            # returns without hanging. Some providers may legitimately
            # return None if unavailable, so we don't assert on the
            # response content here.

            print(
                f"[{datetime.now()}] SUCCESS: Program terminated properly!"
            )

    except KeyboardInterrupt:
        pytest.fail(
            "Agent execution timed out and did not terminate"
        )

    finally:
        timer.cancel()