"""Counting rules of benchmarks/execution_benchmark.py, with fake runners.

No framework is imported and nothing leaves the machine: each runner is a
``build()`` that returns the call to time, as the script's real runners do.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "benchmarks" / "execution_benchmark.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("execution_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runner(answers, log, name):
    """A build() whose calls return ``answers`` in order (an Exception is raised)."""
    answers = iter(answers)

    def build():
        log.append(("build", name))

        def call():
            log.append(("call", name))
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return call
    return build


def test_warm_up_calls_are_not_timed_and_rounds_interleave(bench):
    log = []
    runners = {"A": runner(["w", "a1", "a2"], log, "A"), "B": runner(["w", "b1", "b2"], log, "B")}
    results = bench.run_benchmark(runners, iterations=2, warmup=1)
    assert [len(r["times"]) for r in results.values()] == [2, 2]
    calls = [name for kind, name in log if kind == "call"]
    assert calls == ["A", "B", "A", "B", "B", "A"]  # warm-ups, round 1, round 2 rotated


def test_errors_and_empty_answers_are_failures_not_timings(bench):
    log = []
    runners = {"A": runner(["w", RuntimeError("401"), None, "None", "  ", "4"], log, "A")}
    results = bench.run_benchmark(runners, iterations=5, warmup=1)
    assert len(results["A"]["times"]) == 1
    assert len(results["A"]["failures"]) == 4
    assert "RuntimeError: 401" in results["A"]["failures"][0]


def test_a_failed_warm_up_does_not_drop_the_framework(bench):
    log = []
    runners = {"A": runner([RuntimeError("timeout"), "a1", "a2"], log, "A")}
    results = bench.run_benchmark(runners, iterations=2, warmup=1)
    assert len(results["A"]["times"]) == 2


def test_summary_ranks_by_median_and_skips_frameworks_without_a_success(bench):
    results = {
        "slow": {"times": [1.0, 1.1, 9.0], "failures": []},
        "fast": {"times": [0.5, 0.6, 0.7], "failures": ["x"]},
        "broken": {"times": [], "failures": ["401"]},
    }
    rows = bench.summarise(results)
    assert [r[0] for r in rows] == ["fast", "slow"]
    name, median, mean, ok, failed = rows[1]
    assert (median, ok, failed) == (1.1, 3, 0)
    assert mean == pytest.approx(11.1 / 3)


def test_only_the_call_is_timed(bench, monkeypatch):
    clock = iter([10.0, 10.5])  # start / end of the one timed call; build() reads no clock

    def build():
        return lambda: "4"

    monkeypatch.setattr(bench.time, "perf_counter", lambda: next(clock))
    results = bench.run_benchmark({"A": build}, iterations=1, warmup=0)
    assert results["A"]["times"] == [0.5]
