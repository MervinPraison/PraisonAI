#!/usr/bin/env python3
"""
Regression test for telemetry cleanup at interpreter shutdown.

The hang this guards against happens at *process termination* (via atexit
handlers / object destructors), not during ``agent.start()``. Asserting on the
return value alone would not exercise it, so the agent is run inside a bounded
child process and we require that child to exit cleanly within a deadline.
"""

import os
import sys
import subprocess
import textwrap

import pytest


# Child program: run a single agent turn with telemetry disabled, then let the
# interpreter shut down normally. If telemetry cleanup hangs, the process will
# not exit and the parent's timeout below will fail the test deterministically.
_CHILD_PROGRAM = textwrap.dedent(
    """
    import os
    os.environ["PRAISONAI_TELEMETRY_DISABLED"] = "true"

    from praisonaiagents import Agent

    agent = Agent(instructions="You are a helpful assistant", llm="gpt-4o-mini")
    response = agent.start("Hello, just say hi back!")
    assert response is not None, "agent returned no response"
    print("AGENT_OK")
    """
)


@pytest.mark.integration
def test_agent_terminates_without_hanging():
    """Agent completes and the process exits within a bounded deadline.

    Runs in a child process so that a telemetry-cleanup regression manifests as
    a timeout (test failure) rather than hanging the pytest worker, and so the
    ``PRAISONAI_TELEMETRY_DISABLED`` setting cannot leak into other tests.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for this integration test")

    try:
        result = subprocess.run(
            [sys.executable, "-c", _CHILD_PROGRAM],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "Agent process did not terminate within 120s; "
            "telemetry cleanup likely hangs at shutdown."
        )

    assert result.returncode == 0, (
        f"Child process exited with {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "AGENT_OK" in result.stdout, (
        f"Agent did not complete successfully.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
