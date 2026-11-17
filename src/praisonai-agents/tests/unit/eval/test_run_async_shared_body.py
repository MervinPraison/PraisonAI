"""G-30: the three evaluators' identical ``run_async`` bodies share one helper.

Characterisation test (passes before and after the merge): ``run_async``
awaits the async before-hook, runs the sync ``run(print_summary=False)``,
awaits the async after-hook with its result, prints the summary only when
asked, and returns the result.
"""

import asyncio

import pytest

from praisonaiagents.eval.accuracy import AccuracyEvaluator
from praisonaiagents.eval.criteria import CriteriaEvaluator
from praisonaiagents.eval.performance import PerformanceEvaluator


class _Result:
    def __init__(self, calls):
        self.calls = calls

    def print_summary(self):
        self.calls.append("print_summary")


def _evaluator(cls, calls):
    ev = cls.__new__(cls)  # run_async only touches the hooks and run()
    result = _Result(calls)

    async def before():
        calls.append("async_before_run")

    async def after(r):
        calls.append(("async_after_run", r is result))

    def run(print_summary=False):
        calls.append(("run", print_summary))
        return result

    ev.async_before_run, ev.async_after_run, ev.run = before, after, run
    return ev, result


@pytest.mark.parametrize("cls", [AccuracyEvaluator, CriteriaEvaluator, PerformanceEvaluator])
@pytest.mark.parametrize("print_summary", [False, True])
def test_run_async_order_and_result(cls, print_summary):
    calls = []
    ev, result = _evaluator(cls, calls)
    assert asyncio.run(ev.run_async(print_summary=print_summary)) is result
    expected = ["async_before_run", ("run", False), ("async_after_run", True)]
    assert calls == expected + (["print_summary"] if print_summary else [])


@pytest.mark.parametrize("cls", [AccuracyEvaluator, CriteriaEvaluator, PerformanceEvaluator])
def test_run_async_default_is_no_summary(cls):
    calls = []
    ev, _ = _evaluator(cls, calls)
    asyncio.run(ev.run_async())
    assert "print_summary" not in calls
