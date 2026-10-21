"""Input validation must not run blocking validators on the achat event loop."""
import asyncio
import threading

import pytest

from praisonaiagents import Agent


class RecordingInputGuardrail:
    """Reject before provider dispatch while recording the execution thread."""

    def __init__(self):
        self.thread_id = None
        self.content = None

    def validate_input(self, content, **kwargs):
        self.thread_id = threading.get_ident()
        self.content = content
        return False, "blocked by test validator"

    def validate_output(self, content, **kwargs):
        return True, content


def test_achat_offloads_sync_input_guardrail():
    """Public achat invokes a synchronous validator outside its event-loop thread."""
    guardrail = RecordingInputGuardrail()
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=guardrail)

    async def run():
        loop_thread = threading.get_ident()
        await agent.achat("blocked prompt")
        assert guardrail.content == "blocked prompt"
        assert guardrail.thread_id is not None
        assert guardrail.thread_id != loop_thread

    asyncio.run(run())


@pytest.mark.parametrize("guardrails", [None, "Check output quality", lambda output: (True, output)])
def test_achat_disabled_guardrail_keeps_fast_path(monkeypatch, guardrails):
    """Absent, callable and output-only guards need no worker-thread dispatch."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=guardrails)
    guardrail = RecordingInputGuardrail()

    def record(prompt):
        guardrail.validate_input(prompt)
        return False, None, "stop before provider dispatch"

    monkeypatch.setattr(agent, "_validate_input_with_guardrail", record)
    asyncio.run(agent.achat("blocked prompt"))
    assert guardrail.thread_id == threading.get_ident()


def test_chat_keeps_sync_input_guardrail_on_caller_thread():
    """The synchronous public API retains its existing execution context."""
    guardrail = RecordingInputGuardrail()
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=guardrail)
    agent.chat("blocked prompt")
    assert guardrail.content == "blocked prompt"
    assert guardrail.thread_id == threading.get_ident()
