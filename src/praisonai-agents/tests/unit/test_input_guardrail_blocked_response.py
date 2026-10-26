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


@pytest.mark.parametrize("stream", [False, True])
def test_start_backend_rejection_never_dispatches(monkeypatch, stream):
    """Reject backend prompts before delegation in either streaming mode."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    agent.backend = object()
    delegate = MagicMock(return_value="backend output")
    monkeypatch.setattr(agent, "_delegate_to_backend", delegate)
    result = agent.start("blocked prompt", stream=stream)
    if stream:
        result = "".join(result)
    assert result == agent._guardrail_blocked_message()
    delegate.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
def test_backend_receives_validated_prompt(monkeypatch, stream):
    """Pass the once-validated prompt and original return shape to the backend."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini")
    agent.backend = object()
    monkeypatch.setattr(agent, "_validate_input_with_guardrail",
                        lambda prompt: (True, "validated prompt", None))
    response = iter(("backend output",)) if stream else "backend output"
    delegate = MagicMock(return_value=response)
    monkeypatch.setattr(agent, "_delegate_to_backend", delegate)
    assert agent.start("original prompt", stream=stream) is response
    delegate.assert_called_once_with("validated prompt", stream=stream)


def test_planning_rejects_before_creating_plan(monkeypatch):
    """No planner runs for rejected input."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    planner = MagicMock()
    planner.create_plan_sync.return_value = None
    monkeypatch.setattr(agent, "_get_planning_agent", lambda: planner)
    result = agent._start_with_planning("blocked prompt")
    assert result == agent._guardrail_blocked_message()
    planner.create_plan_sync.assert_not_called()


@pytest.mark.parametrize("blocked", [False, True])
def test_planning_stops_after_blocked_step(monkeypatch, blocked):
    """Only accepted steps proceed to later steps and compilation."""
    from types import SimpleNamespace

    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini")
    plan = MagicMock()
    plan.steps = [SimpleNamespace(description="first"), SimpleNamespace(description="second")]
    plan.to_markdown.return_value = "two steps"
    planner = MagicMock()
    planner.create_plan_sync.return_value = plan
    monkeypatch.setattr(agent, "_get_planning_agent", lambda: planner)
    first = agent._guardrail_blocked_message() if blocked else "first result"
    chat = MagicMock(side_effect=[first, "second result", "compiled result"])
    monkeypatch.setattr(agent, "chat", chat)
    monkeypatch.setattr(agent, "_validate_input_with_guardrail",
                        lambda prompt: (True, "validated prompt", None))
    result = agent._start_with_planning("accepted prompt")
    planner.create_plan_sync.assert_called_once_with(request="validated prompt", agents=[agent])
    if blocked:
        assert result is first
        chat.assert_called_once_with("first")
    else:
        assert result == "compiled result"
        assert chat.call_count == 3


@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("is_async", [False, True])
def test_caller_mode_preserves_rejection_status(monkeypatch, blocked, is_async):
    """Sync and async caller results distinguish safe rejection from success."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", autonomy=True)
    response = agent._guardrail_blocked_message() if blocked else "normal response"
    monkeypatch.setattr(agent, "chat", lambda *a, **k: response)
    monkeypatch.setattr(agent, "achat", AsyncMock(return_value=response))
    monkeypatch.setattr(agent, "_load_history_context", lambda: None)
    monkeypatch.setattr(agent, "_auto_save_session", lambda: None)
    result = asyncio.run(agent.astart("prompt")) if is_async else agent.start("prompt")
    assert result.success is (not blocked)
    assert result.output == response
    assert result.error == (response if blocked else None)


@pytest.mark.parametrize("autonomy", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
def test_async_outcome_preserves_guardrail_failure(monkeypatch, autonomy, blocked):
    """Canonical outcomes must not turn rejected caller results into success."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", autonomy=autonomy)
    response = agent._guardrail_blocked_message() if blocked else "normal response"
    monkeypatch.setattr(agent, "achat", AsyncMock(return_value=response))
    monkeypatch.setattr(agent, "_auto_save_session", lambda: None)
    outcome = asyncio.run(agent.astart("prompt", return_outcome=True))
    assert outcome.reason == ("failed" if blocked else "completed")
    assert outcome.error == (str(response) if blocked else None)


def test_planning_outcome_preserves_guardrail_failure(monkeypatch):
    """A rejected planning request is failed even before a provider stop reason exists."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    agent.planning = True
    monkeypatch.setattr(agent, "_get_planning_agent", MagicMock())
    outcome = agent.run("blocked prompt", return_outcome=True)
    assert outcome.reason == "failed"
    assert outcome.output == agent._guardrail_blocked_message()
    assert outcome.error == outcome.output
    agent._get_planning_agent.assert_not_called()


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
