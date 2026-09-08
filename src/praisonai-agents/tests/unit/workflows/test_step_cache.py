"""Workflow steps can cache their results by input.

Prompt caching existed; caching a STEP's output by input key did not, so a
deterministic step paid full price on every re-run -- felt most while iterating
on the steps after it.
"""
import pytest

from praisonaiagents.workflows.step_cache import (
    InMemoryStepCache,
    make_step_key,
    resolve_step_cache,
)
from praisonaiagents.workflows.workflows import AgentFlow, Parallel


def _counting_step(name, calls):
    def handler(ctx):
        calls.append(name)
        return f"{name}-output"
    handler.__name__ = name
    return handler


class TestCachingWorks:
    def test_an_identical_run_reuses_the_result(self):
        calls = []
        flow = AgentFlow(steps=[_counting_step("s", calls)], cache=True)
        flow.run("same", verbose=False)
        flow.run("same", verbose=False)
        assert calls == ["s"]

    def test_control_an_uncached_flow_runs_every_time(self):
        calls = []
        flow = AgentFlow(steps=[_counting_step("s", calls)])
        flow.run("same", verbose=False)
        flow.run("same", verbose=False)
        assert calls == ["s", "s"]

    def test_a_different_input_is_not_a_hit(self):
        calls = []
        flow = AgentFlow(steps=[_counting_step("s", calls)], cache=True)
        flow.run("A", verbose=False)
        flow.run("B", verbose=False)
        assert calls == ["s", "s"]

    def test_steps_inside_a_pattern_are_cached_too(self):
        """Both executors are wrapped: caching only the linear path would make
        the feature work or not depending on where a step happened to sit."""
        calls = []
        flow = AgentFlow(steps=[Parallel(steps=[_counting_step("p", calls)])], cache=True)
        flow.run("same", verbose=False)
        flow.run("same", verbose=False)
        assert calls == ["p"]


class TestKeys:
    def test_the_same_inputs_key_the_same(self):
        a = make_step_key("step", "prev", "in", {"x": 1})
        b = make_step_key("step", "prev", "in", {"x": 1})
        assert a == b

    @pytest.mark.parametrize("changed", [
        {"step": "other"}, {"previous_output": "different"},
        {"input_text": "different"}, {"variables": {"x": 2}},
    ])
    def test_any_input_change_changes_the_key(self, changed):
        base = dict(step="step", previous_output="prev", input_text="in", variables={"x": 1})
        assert make_step_key(**base) != make_step_key(**{**base, **changed})

    def test_variables_are_part_of_the_key(self):
        """Two runs with the same prompt but different variables are different
        calls; sharing an entry would serve one run's answer to another."""
        a = make_step_key("s", None, "in", {"user": "alice"})
        b = make_step_key("s", None, "in", {"user": "bob"})
        assert a != b


class TestTheCacheItself:
    def test_it_is_bounded(self):
        """Unbounded would be a memory leak that only shows up in production."""
        cache = InMemoryStepCache(max_entries=2)
        for i in range(5):
            cache.set(f"k{i}", {"output": i})
        assert len(cache) == 2

    def test_it_evicts_least_recently_used(self):
        cache = InMemoryStepCache(max_entries=2)
        cache.set("a", {"output": 1})
        cache.set("b", {"output": 2})
        cache.get("a")            # a is now most recent
        cache.set("c", {"output": 3})
        assert cache.get("a") is not None
        assert cache.get("b") is None

    def test_a_zero_size_cache_is_refused(self):
        with pytest.raises(ValueError, match="positive"):
            InMemoryStepCache(max_entries=0)

    def test_hits_and_misses_are_counted(self):
        cache = InMemoryStepCache()
        cache.get("nope")
        cache.set("k", {"output": 1})
        cache.get("k")
        assert (cache.hits, cache.misses) == (1, 1)


class TestResolution:
    def test_true_gives_a_cache(self):
        assert isinstance(resolve_step_cache(True), InMemoryStepCache)

    @pytest.mark.parametrize("value", [None, False])
    def test_control_falsey_means_no_caching(self, value):
        assert resolve_step_cache(value) is None

    def test_a_custom_object_is_accepted(self):
        cache = InMemoryStepCache()
        assert resolve_step_cache(cache) is cache

    def test_a_nonsense_value_is_refused(self):
        with pytest.raises(TypeError, match="get\\(\\)/set\\(\\)"):
            resolve_step_cache("yes please")
