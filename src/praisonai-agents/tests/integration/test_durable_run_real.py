"""Opt-in real-provider smoke for durable Agent execution."""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1",
    reason="requires an explicitly enabled real provider",
)
def test_real_agent_records_durable_tool_step(tmp_path):
    from praisonaiagents import Agent, ExecutionConfig
    from praisonaiagents.runtime import RunJournal
    from praisonaiagents.runtime.journal import KIND_TOOL_RESULT

    calls = []

    def durable_echo(text: str) -> str:
        """Echo text while recording the external side effect."""
        calls.append(text)
        return text

    journal_path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-real-smoke",
        instructions="Call durable_echo once, then report its exact result.",
        tools=[durable_echo],
        execution=ExecutionConfig(
            durable=True,
            journal_path=journal_path,
            max_steps=3,
        ),
    )
    result = agent.start("Call durable_echo with the text NEBULA-7.")

    print(result)
    assert calls == ["NEBULA-7"]
    journal = RunJournal(journal_path)
    events = journal.events(agent._last_durable_run_id)
    journal.close()
    assert any(event.kind == KIND_TOOL_RESULT for event in events)
