"""The whole-task retry must know why the last attempt was rejected.

``AgentTeam._apply_task_guardrail`` re-runs a task whose guardrail failed, but
it used to re-run it with the identical prompt: the reason was logged and
dropped, so the model had no way to do anything different.  Task already has a
``validation_feedback`` slot that ``Process._build_task_context`` turns into
"Previous attempt failed validation with reason: ..." - these tests pin the
guardrail failure into that existing wiring.

This is the *outer* loop: the agent corrects itself in-run first (see
tests/unit/agent/test_guardrail_retry_feedback.py); only when that is exhausted
does the task get re-run.
"""
import pytest

from praisonaiagents import Agent, Task, TaskOutput
from praisonaiagents.agents import AgentTeam
from praisonaiagents.guardrails import GuardrailRetry
from praisonaiagents.process import Process

REASON = "the total must include VAT"


def rejects(output):
    return False, REASON


def rejects_by_raising(output):
    raise GuardrailRetry(REASON)


def accepts(output):
    return True, output


def _team(guardrail, max_retries=2):
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini")
    task = Task(name="t", description="add up the invoice", expected_output="a total",
                agent=agent, guardrail=guardrail, max_retries=max_retries)
    return AgentTeam(agents=[agent], tasks=[task]), task


def _output(raw="100.00"):
    return TaskOutput(description="add up the invoice", raw=raw, agent="A")


class TestRejectionReachesTheRerun:
    def test_feedback_is_stored_for_the_next_attempt(self):
        team, task = _team(rejects)
        _out, should_retry = team._apply_task_guardrail(task, "t1", _output())
        assert should_retry is True
        assert task.retry_count == 1
        assert task.validation_feedback["validation_response"] == REASON
        assert task.validation_feedback["rejected_output"] == "100.00"

    def test_raised_guardrail_retry_stores_the_same_feedback(self):
        team, task = _team(rejects_by_raising)
        _out, should_retry = team._apply_task_guardrail(task, "t1", _output())
        assert should_retry is True
        assert task.validation_feedback["validation_response"] == REASON

    def test_control_passing_guardrail_stores_nothing(self):
        team, task = _team(accepts)
        _out, should_retry = team._apply_task_guardrail(task, "t1", _output())
        assert should_retry is False
        assert task.retry_count == 0
        assert task.validation_feedback is None

    def test_stored_feedback_is_rendered_into_the_next_prompt(self):
        team, task = _team(rejects)
        team._apply_task_guardrail(task, "t1", _output())

        process = Process(agents={"A": task.agent}, tasks={"t": task}, verbose=0)
        context = process._build_task_context(task)
        assert REASON in context, "the reason never reached the re-run's prompt"
        assert "100.00" in context, "the rejected output was not shown to the model"
        assert task.validation_feedback is None, "feedback must be consumed once"

    def test_control_no_feedback_no_validation_preamble(self):
        team, task = _team(accepts)
        team._apply_task_guardrail(task, "t1", _output())

        process = Process(agents={"A": task.agent}, tasks={"t": task}, verbose=0)
        context = process._build_task_context(task)
        assert REASON not in context
        assert "failed validation" not in context

    def test_exhausting_max_retries_raises_with_the_reason(self):
        team, task = _team(rejects, max_retries=1)
        team._apply_task_guardrail(task, "t1", _output())  # retry_count -> 1
        with pytest.raises(Exception) as excinfo:
            team._apply_task_guardrail(task, "t1", _output())
        message = str(excinfo.value)
        assert "after 1 retries" in message, message
        assert REASON in message, message
