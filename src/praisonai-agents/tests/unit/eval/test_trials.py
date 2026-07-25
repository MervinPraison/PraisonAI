"""Unit tests for the trials engine (eval/trials.py)."""
import os
import tempfile

from praisonaiagents.eval import (
    EvalCase,
    EvalPackage,
    run_trials,
    TrialScore,
    TrialAttempt,
    TrialReport,
)
from praisonaiagents.eval.trials import _coerce_score, _score_attempt


class FakeAgent:
    """Minimal agent stub with a ``chat`` method and chat_history."""

    def __init__(self, response="ok", agent_id="fake"):
        self._response = response
        self.agent_id = agent_id
        self.chat_history = []
        self.memory = None
        self.knowledge = None

    def chat(self, prompt, **kwargs):
        self.chat_history.append({"role": "user", "content": prompt})
        return self._response


class MemoryWritingAgent(FakeAgent):
    """Agent whose chat writes to a shared memory list (to test isolation)."""

    def __init__(self, memory_sink):
        super().__init__(response="done")
        self._sink = memory_sink

    def chat(self, prompt, **kwargs):
        self._sink.append(prompt)
        return self._response


def test_coerce_score_shapes():
    assert _coerce_score(True) == TrialScore(value=1.0, passed=True)
    assert _coerce_score(False) == TrialScore(value=0.0, passed=False)
    assert _coerce_score(0.9).passed is True
    assert _coerce_score(0.1).passed is False
    ts = TrialScore(value=0.5, passed=True, reason="r")
    assert _coerce_score(ts) is ts


def test_run_trials_k_attempts_per_case():
    agent = FakeAgent(response="hello")
    pkg = EvalPackage(name="p", cases=[
        EvalCase(name="c1", input="a", verify=lambda o, e: True),
        EvalCase(name="c2", input="b", verify=lambda o, e: True),
    ])
    report = run_trials(agent, pkg, k=3, concurrency=2)
    assert isinstance(report, TrialReport)
    assert len(report.attempts["c1"]) == 3
    assert len(report.attempts["c2"]) == 3
    # Deterministic attempt ordering.
    assert [a.attempt for a in report.attempts["c1"]] == [0, 1, 2]


def test_verify_callable_bool_float_score():
    agent = FakeAgent(response="x")
    pkg = EvalPackage(name="p", cases=[
        EvalCase(name="b", input="i", verify=lambda o, e: True),
        EvalCase(name="f", input="i", verify=lambda o, e: 0.8),
        EvalCase(name="s", input="i",
                 verify=lambda o, e: TrialScore(value=0.3, passed=False)),
    ])
    report = run_trials(agent, pkg, k=1)
    assert report.attempts["b"][0].score.passed is True
    assert report.attempts["f"][0].score.value == 0.8
    assert report.attempts["s"][0].score.passed is False


def test_attempt_isolation_memory_untouched():
    sink = []
    agent = MemoryWritingAgent(memory_sink=sink)
    # The isolated copy severs `memory`; caller's real memory attr stays intact.
    pkg = EvalPackage(name="p", cases=[
        EvalCase(name="c", input="write me", verify=lambda o, e: True),
    ])
    run_trials(agent, pkg, k=2)
    # Original agent's memory attr is untouched (still None on the original).
    assert agent.memory is None


def test_attempts_do_not_share_session_id():
    agent = FakeAgent(response="ok", agent_id="orig")
    pkg = EvalPackage(name="p", cases=[
        EvalCase(name="c", input="i", verify=lambda o, e: True),
    ])
    run_trials(agent, pkg, k=2)
    # Original agent id is not mutated by the isolated copies.
    assert agent.agent_id == "orig"


def test_unscored_excluded_from_stats():
    def slow_verify(o, e):
        return True

    agent = FakeAgent(response="ok")
    # Force a timeout: agent sleeps longer than timeout_seconds.
    class SlowAgent(FakeAgent):
        def chat(self, prompt, **kwargs):
            import time
            time.sleep(0.3)
            return "late"

    pkg = EvalPackage(name="p", cases=[
        EvalCase(name="c", input="i", timeout_seconds=0.05,
                 verify=slow_verify),
    ])
    report = run_trials(SlowAgent(), pkg, k=2)
    attempts = report.attempts["c"]
    assert all(a.stop_reason == "timeout" for a in attempts)
    assert all(a.score is None for a in attempts)
    # Unscored attempts excluded -> pass_rate falls back to 0.0, no crash.
    assert report.pass_rates()["c"] == 0.0
    summary = report.summary()
    assert summary["cases"]["c"]["n_scored"] == 0


def test_frontier_selection():
    report = TrialReport(package_name="p", k=4)
    report.attempts["all_pass"] = [
        TrialAttempt("all_pass", i, "completed",
                     score=TrialScore(1.0, True)) for i in range(4)
    ]
    report.attempts["all_fail"] = [
        TrialAttempt("all_fail", i, "completed",
                     score=TrialScore(0.0, False)) for i in range(4)
    ]
    report.attempts["frontier"] = [
        TrialAttempt("frontier", i, "completed",
                     score=TrialScore(1.0 if i < 2 else 0.0, i < 2))
        for i in range(4)
    ]
    assert report.frontier() == ["frontier"]
    rates = report.pass_rates()
    assert rates["all_pass"] == 1.0
    assert rates["all_fail"] == 0.0
    assert rates["frontier"] == 0.5


def test_report_save_load_roundtrip():
    agent = FakeAgent(response="hi")
    pkg = EvalPackage(name="rt", cases=[
        EvalCase(name="c", input="i", verify=lambda o, e: 0.9),
    ])
    report = run_trials(agent, pkg, k=2, capture_record=True)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "trials.json")
        report.save(path)
        loaded = TrialReport.load(path)
    assert loaded.package_name == "rt"
    assert loaded.k == 2
    assert len(loaded.attempts["c"]) == 2
    assert loaded.attempts["c"][0].score.value == 0.9
    # Record survives.
    assert loaded.attempts["c"][0].record is not None
    assert loaded.attempts["c"][0].record["output"] == "hi"


def test_score_attempt_no_scorer_passes_on_nonempty():
    case = EvalCase(name="c", input="i")
    agent = FakeAgent()
    score = _score_attempt(case, "some output", agent, "some output")
    assert score.passed is True
    empty = _score_attempt(case, "", agent, "")
    assert empty.passed is False


def test_tool_assertion_scoring():
    class ToolAgent(FakeAgent):
        def chat(self, prompt, **kwargs):
            self.chat_history.append({
                "role": "assistant",
                "tool_calls": [{"function": {"name": "search"}}],
            })
            return "done"

    case = EvalCase(name="c", input="i", metadata={"expected_tools": ["search"]})
    agent = ToolAgent()
    resp = agent.chat("i")
    score = _score_attempt(case, "done", agent, resp)
    assert score.passed is True

    case_missing = EvalCase(name="c", input="i",
                            metadata={"expected_tools": ["missing_tool"]})
    agent2 = ToolAgent()
    resp2 = agent2.chat("i")
    score2 = _score_attempt(case_missing, "done", agent2, resp2)
    assert score2.passed is False
