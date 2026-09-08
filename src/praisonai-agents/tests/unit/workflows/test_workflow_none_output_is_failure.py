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


class TestContinuedFailureKeepsItsReason:
    """A None-output step with on_error='continue' must still carry its reason.

    The run continues past the failed step, so it takes the general result path
    rather than the on_error='stop' branch. That path used to omit the step's
    error, so the final result fell back to the generic 'step(s) failed: <name>'
    text instead of the computed 'agent produced no output' diagnostic.
    """

    def test_continued_none_step_reports_its_reason_not_the_generic_fallback(self):
        first = Task(
            name="first", agent=_NullAgent(), action="do it", max_retries=0
        )
        first.on_error = "continue"
        wf = Workflow(
            name="continue-flow",
            steps=[
                first,
                Task(name="second", agent=_RealAgent(), action="Write a haiku", max_retries=0),
            ],
        )
        result = wf.start("go")
        assert result["status"] == "failed"
        failed = [s for s in result["steps"] if s.get("status") == "failed"]
        assert failed and failed[0]["step"] == "first"
        assert "produced no output" in (failed[0].get("error") or ""), (
            "a continued failure lost its diagnostic reason"
        )
        assert "produced no output" in result.get("error", ""), (
            "the final result must surface the real reason, not the fallback"
        )


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


class TestHierarchicalManagerVerdictFailsClosed:
    """A manager rejection must not be silently turned into approval.

    `process="hierarchical"` asks a manager LLM to approve each step and parsed
    the reply with a bare ``json.loads``. Models routinely fence JSON in
    ```json ... ```, which raises JSONDecodeError -- and the handler then FAILED
    OPEN, substituting ``{"approved": True, "reason": "...assuming success"}``.

    So the manager answered `{"approved": false, "reason": "The output is empty
    and does not address the task."}` and the run still reported "completed":
    the whole validation feature was a no-op for rejections.

    These use an agent that DOES produce output, so the manager is genuinely
    consulted and it is the verdict handling under test.
    """

    def _workflow(self, agent):
        return Workflow(
            name="hier",
            process="hierarchical",
            steps=[Task(name="haiku", agent=agent, action="write a haiku",
                        max_retries=0)],
        )

    def _stub_manager(self, monkeypatch, reply):
        """Make the manager LLM return `reply` without any network call."""
        from praisonaiagents.llm import LLM

        monkeypatch.setattr(
            LLM, "get_response",
            lambda self, *a, **k: reply,
            raising=False,
        )

    def test_a_fenced_rejection_fails_the_run(self, monkeypatch):
        self._stub_manager(
            monkeypatch,
            '```json\n{"approved": false, "reason": "Off topic."}\n```',
        )
        result = self._workflow(_RealAgent()).start("go")
        assert result["status"] == "failed", (
            "a fenced manager rejection was silently treated as approval"
        )

    def test_a_bare_rejection_still_fails_the_run(self, monkeypatch):
        self._stub_manager(
            monkeypatch, '{"approved": false, "reason": "Off topic."}'
        )
        assert self._workflow(_RealAgent()).start("go")["status"] == "failed"

    def test_the_rejection_reason_is_reported(self, monkeypatch):
        self._stub_manager(
            monkeypatch,
            '```json\n{"approved": false, "reason": "Off topic."}\n```',
        )
        result = self._workflow(_RealAgent()).start("go")
        assert "Off topic." in result.get("failure_reason", "")

    def test_a_fenced_approval_still_completes(self, monkeypatch):
        """The fence fix must work in both directions, not just reject."""
        self._stub_manager(
            monkeypatch,
            '```json\n{"approved": true, "reason": "Looks good."}\n```',
        )
        assert self._workflow(_RealAgent()).start("go")["status"] == "completed"

    def test_an_unparseable_verdict_fails_closed(self, monkeypatch):
        """An unreadable verdict is not approval."""
        self._stub_manager(monkeypatch, "I could not decide, sorry.")
        result = self._workflow(_RealAgent()).start("go")
        assert result["status"] == "failed", (
            "an unparseable manager verdict was treated as approval"
        )


class TestHierarchicalRunsAreJudgedToo:
    """`process="hierarchical"` had the reported defect in full.

    Its loop marked every non-raising step "completed" before the manager saw
    it, and skipped validation entirely when the manager LLM call itself raised
    -- so with a dead API key the step produced nothing, the gate never ran, and
    the CLI printed "Workflow completed successfully!" and exited 0.
    """

    def _workflow(self, agent):
        return Workflow(
            name="hier",
            process="hierarchical",
            steps=[Task(name="haiku", agent=agent, action="write a haiku",
                        max_retries=0)],
        )

    def test_a_step_producing_nothing_fails_the_run(self, monkeypatch):
        """Reaches the verdict without the manager needing to run at all."""
        from praisonaiagents.llm import LLM

        def _boom(self, *a, **k):
            raise AssertionError("the manager must not be consulted")

        monkeypatch.setattr(LLM, "get_response", _boom, raising=False)
        wf = self._workflow(_NullAgent())
        result = wf.start("go")
        assert result["status"] == "failed"
        # The step itself must be recorded failed too, not merely the run: the
        # per-step record is what `--save` writes out and what callers read.
        assert [s_["status"] for s_ in result["steps"]] == ["failed"]
        assert wf.step_statuses["haiku"] == "failed"

    def test_that_failure_is_reported_under_the_error_key(self, monkeypatch):
        """The CLI reads `error`; hierarchical only set `failure_reason`."""
        from praisonaiagents.llm import LLM

        monkeypatch.setattr(
            LLM, "get_response", lambda self, *a, **k: "", raising=False
        )
        result = self._workflow(_NullAgent()).start("go")
        assert result.get("error"), "a failed run must say why under `error`"
        assert "haiku" in result["error"]

    def test_a_manager_outage_does_not_report_success(self, monkeypatch):
        """If the gate cannot run, the gate has not passed."""
        from praisonaiagents.llm import LLM

        def _raise(self, *a, **k):
            raise RuntimeError("401 Incorrect API key provided")

        monkeypatch.setattr(LLM, "get_response", _raise, raising=False)
        result = self._workflow(_RealAgent()).start("go")
        assert result["status"] == "failed", (
            "manager validation failed and the run still reported success"
        )
        assert "401" in result.get("error", "")

    def test_a_healthy_hierarchical_run_still_completes(self, monkeypatch):
        """None of this may break a run that genuinely worked."""
        from praisonaiagents.llm import LLM

        monkeypatch.setattr(
            LLM, "get_response",
            lambda self, *a, **k: '{"approved": true, "reason": "Good."}',
            raising=False,
        )
        result = self._workflow(_RealAgent()).start("go")
        assert result["status"] == "completed"
        assert "error" not in result
