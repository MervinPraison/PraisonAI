"""A workflow whose only agent step produced nothing must not report success.

`Agent.chat()` returns ``None`` when the underlying model call failed and the
agent swallowed the error -- an invalid API key is the common case. The engine
already logged "Step 'x': Output is None" and then still set
``status == "completed"``, so `praisonai workflow run` printed
"Workflow completed successfully!" over a run in which nothing happened, and
every other consumer of ``Workflow.start()`` (the API server, Python callers)
was told the same.

The verdict belongs in the engine, not in one CLI: only here is it known
whether the step was LLM-backed (an output is definitionally expected) or a
custom ``handler`` (which may legitimately return ``None``).
"""

from praisonaiagents import Workflow, StepResult
from praisonaiagents.task.task import Task


class _NullAgent:
    """Stands in for an Agent whose model call failed and returned nothing."""

    name = "Writer"

    def __init__(self):
        self.calls = 0

    def chat(self, action, **kwargs):
        self.calls += 1
        return None


class _RealAgent:
    name = "Writer"

    def chat(self, action, **kwargs):
        return "a haiku"


class TestAgentStepProducingNothingFailsTheRun:

    def test_status_is_failed_when_the_only_agent_step_returns_none(self):
        agent = _NullAgent()
        wf = Workflow(
            name="haiku-flow",
            steps=[Task(name="haiku", agent=agent, action="Write a haiku", max_retries=0)],
        )
        result = wf.start("Write a haiku about testing")
        assert result["status"] == "failed", (
            "a run whose only step produced nothing reported success: "
            f"{result['status']!r}"
        )

    def test_the_failed_step_is_named_in_the_result(self):
        wf = Workflow(
            name="haiku-flow",
            steps=[Task(name="haiku", agent=_NullAgent(), action="Write a haiku", max_retries=0)],
        )
        result = wf.start("go")
        failed = [s for s in result["steps"] if s.get("status") == "failed"]
        assert [s["step"] for s in failed] == ["haiku"]

    def test_the_result_carries_a_reason_not_unknown_error(self):
        wf = Workflow(
            name="haiku-flow",
            steps=[Task(name="haiku", agent=_NullAgent(), action="Write a haiku", max_retries=0)],
        )
        result = wf.start("go")
        assert result.get("error"), "a failed run must say why it failed"
        assert "haiku" in result["error"]

    def test_a_later_step_does_not_run_after_one_produces_nothing(self):
        """The default on_error is 'stop': don't feed None forward."""
        second = _RealAgent()
        ran = []

        def _handler(ctx):
            ran.append("second")
            return StepResult(output="second ran")

        wf = Workflow(
            name="two-step",
            steps=[
                Task(name="first", agent=_NullAgent(), action="do it", max_retries=0),
                Task(name="second", handler=_handler, max_retries=0),
            ],
        )
        result = wf.start("go")
        assert result["status"] == "failed"
        assert ran == [], "the workflow kept going after a step produced nothing"

    def test_a_working_agent_step_still_completes(self):
        """The new verdict must not fail runs that genuinely succeeded."""
        wf = Workflow(
            name="haiku-flow",
            steps=[Task(name="haiku", agent=_RealAgent(), action="Write a haiku", max_retries=0)],
        )
        result = wf.start("go")
        assert result["status"] == "completed"
        assert result["output"] == "a haiku"
        assert "error" not in result


class TestHandlerStepsAreNotJudgedThisWay:
    """A custom handler returning None is legitimate -- leave it alone."""

    def test_a_handler_returning_none_still_completes(self):
        def _handler(ctx):
            return None

        wf = Workflow(
            name="handler-flow",
            steps=[Task(name="side-effect", handler=_handler, max_retries=0)],
        )
        result = wf.start("go")
        assert result["status"] == "completed", (
            "a handler step legitimately returning None was marked failed"
        )

    def test_a_handler_returning_a_stepresult_with_no_output_still_completes(self):
        def _handler(ctx):
            return StepResult(output=None)

        wf = Workflow(
            name="handler-flow",
            steps=[Task(name="side-effect", handler=_handler, max_retries=0)],
        )
        assert wf.start("go")["status"] == "completed"
