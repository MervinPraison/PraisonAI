"""Rejected input has the same fixed string contract as rejected output."""
import asyncio

import pytest

from praisonaiagents import Agent, AgentTeam, Task


class RejectInput:
    """Reject input before model dispatch with a diagnostic-only reason."""

    def validate_input(self, content, **kwargs):
        return False, "synthetic validator diagnostic"

    def validate_output(self, content, **kwargs):
        return True, content


@pytest.mark.parametrize("entry", ["chat", "achat", "start", "stream"])
def test_rejected_input_returns_fixed_guardrail_message(entry):
    """All public entry points return usable text, not None or diagnostics."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    expected = agent._guardrail_blocked_message()
    if entry == "achat":
        result = asyncio.run(agent.achat("blocked prompt"))
    elif entry == "stream":
        result = "".join(agent.start("blocked prompt", stream=True))
    else:
        result = getattr(agent, entry)("blocked prompt")
    assert isinstance(result, str)
    assert result == expected
    assert result.strip()


@pytest.mark.parametrize("is_async", [False, True])
def test_team_does_not_complete_or_save_rejected_input(tmp_path, is_async):
    """A text apology must not become a successful task or persisted output."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    path = tmp_path / "output.txt"
    task = Task(name="blocked", description="blocked prompt", agent=agent,
                output_file=str(path), max_retries=1)
    team = AgentTeam(agents=[agent], tasks=[task])
    completed = []
    team.on_task_complete = lambda task, output: completed.append(task)
    if is_async:
        asyncio.run(team.arun_task(0))
    else:
        team.run_task(0)
    assert task.status == "failed"
    assert task.result is None
    assert not path.exists()
    assert completed == []


def test_plain_text_is_not_classified_by_its_message(monkeypatch):
    """Identical ordinary text remains a successful task, without string matching."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini")
    text = str(agent._guardrail_blocked_message())
    monkeypatch.setattr(agent, "chat", lambda *args, **kwargs: text)
    task = Task(name="ordinary", description="test", agent=agent, max_retries=1)
    team = AgentTeam(agents=[agent], tasks=[task])
    team.run_task(0)
    assert task.status == "completed"
    assert task.result.raw == text
