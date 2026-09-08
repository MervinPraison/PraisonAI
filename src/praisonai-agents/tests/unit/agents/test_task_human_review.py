"""A person can be required to sign off a task's OUTPUT.

Two things already existed and neither did this: the approval system gates a
TOOL CALL, and guardrails validate automatically. Nothing let an orchestrator
say "a person must approve this before the next task consumes it".
"""
import pytest

from praisonaiagents import Agent, AgentTeam, Task
from praisonaiagents.approval import ApprovalDecision, get_approval_registry


class _Backend:
    def __init__(self, approved, reason=None):
        self.approved = approved
        self.reason = reason
        self.requests = []

    def request_approval_sync(self, request):
        self.requests.append(request)
        return ApprovalDecision(approved=self.approved, reason=self.reason)

    async def request_approval(self, request):
        return self.request_approval_sync(request)


@pytest.fixture
def team():
    return AgentTeam(agents=[Agent(name="a", instructions="x", llm="gpt-4o")])


def _task(**kwargs):
    task = Task(description="d", expected_output="e", **kwargs)
    task.retry_count, task.max_retries = 0, 2
    return task


class TestReview:
    def test_a_rejection_retries_and_carries_the_reason(self, team):
        get_approval_registry().set_backend(_Backend(False, "needs a citation"))
        task = _task(human_input=True)
        _, should_retry = team._apply_human_review(task, "t1", "draft")
        assert should_retry is True
        assert task.validation_feedback == "needs a citation"
        assert task.retry_count == 1

    def test_an_approval_lets_the_output_through(self, team):
        get_approval_registry().set_backend(_Backend(True))
        task = _task(human_input=True)
        output, should_retry = team._apply_human_review(task, "t1", "draft")
        assert should_retry is False
        assert output == "draft"

    def test_control_a_task_without_human_input_is_never_reviewed(self, team):
        backend = _Backend(False, "would reject")
        get_approval_registry().set_backend(backend)
        task = _task()
        _, should_retry = team._apply_human_review(task, "t1", "draft")
        assert should_retry is False
        assert backend.requests == []

    def test_the_reviewer_sees_the_output(self, team):
        backend = _Backend(True)
        get_approval_registry().set_backend(backend)
        team._apply_human_review(_task(human_input=True), "t1", "the draft text")
        assert "the draft text" in backend.requests[0].arguments["output"]

    def test_a_custom_prompt_reaches_the_reviewer(self, team):
        backend = _Backend(True)
        get_approval_registry().set_backend(backend)
        task = _task(human_input=True, human_review_prompt="Is this legally safe?")
        team._apply_human_review(task, "t1", "draft")
        assert backend.requests[0].context["prompt"] == "Is this legally safe?"


class TestBounds:
    def test_repeated_rejection_stops_at_max_retries(self, team):
        get_approval_registry().set_backend(_Backend(False, "no"))
        task = _task(human_input=True)
        task.retry_count = task.max_retries
        with pytest.raises(Exception, match="rejected by a reviewer"):
            team._apply_human_review(task, "t1", "draft")

    def test_control_a_rejection_within_budget_does_not_raise(self, team):
        get_approval_registry().set_backend(_Backend(False, "no"))
        _, should_retry = team._apply_human_review(_task(human_input=True), "t1", "draft")
        assert should_retry is True


class TestDeclaration:
    def test_task_accepts_human_input(self):
        assert Task(description="d", expected_output="e", human_input=True).human_input is True

    def test_control_it_defaults_off(self):
        assert Task(description="d", expected_output="e").human_input is False
