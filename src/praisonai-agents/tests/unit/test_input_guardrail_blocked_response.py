"""Rejected input has the same fixed string contract as rejected output."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

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
@pytest.mark.parametrize("blocked_stage", ["input", "output"])
def test_team_does_not_complete_or_save_rejected_turn(tmp_path, is_async, blocked_stage):
    """Input and output blocks must not become successful tasks or saved output."""
    guardrails = RejectInput() if blocked_stage == "input" else lambda output: (False, "rejected")
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=guardrails)
    if blocked_stage == "output":
        agent.max_guardrail_retries = 0
        agent._using_custom_llm = True
        agent.llm_instance = MagicMock()
        agent.llm_instance.get_response.return_value = "rejected model output"
        agent.llm_instance.get_response_async = AsyncMock(return_value="rejected model output")
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
