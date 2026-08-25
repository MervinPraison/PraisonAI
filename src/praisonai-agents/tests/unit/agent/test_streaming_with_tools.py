"""Streaming must still produce an answer when a tool is invoked.

The streaming path collects tool calls, executes them, appends the results to
chat history -- and then ends. It never asks the model for the final answer, so
`start(stream=True)` yields nothing while the identical non-streaming call
answers normally.

There is no error. The caller sees an empty generator and cannot tell "the model
had nothing to say" from "the answer was never requested".

Exercised against the real path rather than a mocked client: the defect lives in
the interaction between tool execution and the follow-up completion, which is
precisely what a hand-built mock of that client would define away.
"""

import os

import pytest

from praisonaiagents import Agent

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="exercises the real streaming path; needs a provider credential",
)

SENTINEL = "PRAISONAI-TOOL-SENTINEL"


def sentinel_tool() -> str:
    """Return a fixed marker so a passing assertion cannot be a coincidence."""
    return SENTINEL


def _agent():
    return Agent(name="T", role="Assistant", goal="Answer using your tools.",
                 llm="gpt-4o-mini", tools=[sentinel_tool])


def test_a_plain_turn_streams():
    """Positive control: without tools the path must be unaffected."""
    chunks = [c for c in Agent(name="P", role="Assistant", goal="Answer.",
                               llm="gpt-4o-mini").start("Say hi", stream=True) if c]
    assert chunks, "a plain streamed turn produced nothing; the harness is broken"


def test_a_tool_using_turn_still_streams_an_answer():
    """The regression: a tool round-trip must not swallow the reply.

    Asserting the sentinel flows through the streamed answer proves the tool
    branch actually ran -- a plain answer that never called the tool cannot
    reproduce the marker, so a green test here cannot be a coincidence.
    """
    streamed = "".join(c for c in _agent().start(
        "Call sentinel_tool and tell me exactly what it returned.", stream=True) if c)
    assert streamed, (
        "streaming yielded nothing after a tool call; the follow-up completion "
        "that produces the final answer was never requested"
    )
    assert SENTINEL in streamed, (
        "the sentinel never reached the streamed answer; the tool result was "
        "not carried into the follow-up completion's request context"
    )


def test_streaming_and_non_streaming_agree_when_a_tool_runs():
    """The two paths must not disagree about whether an answer exists."""
    blocking = _agent().start("Call sentinel_tool and report its output.")
    streamed = "".join(c for c in _agent().start(
        "Call sentinel_tool and report its output.", stream=True) if c)
    assert blocking, "non-streaming produced nothing; the harness is broken"
    assert streamed, "streaming produced nothing while non-streaming answered"
