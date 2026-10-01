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
from praisonaiagents.workflows.workflows import AgentFlow, Parallel, StepResult


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


class TestCorrectnessOnAHit:
    @pytest.mark.parametrize("boundary", ["miss", "hit"])
    @pytest.mark.parametrize("field", ["output", "variables", "steps"])
    def test_reference_cache_does_not_share_live_payloads(self, boundary, field):
        class ReferenceCache:
            def __init__(self):
                self.entries = {}

            def get(self, key):
                return self.entries.get(key)

            def set(self, key, value):
                self.entries[key] = value

        calls = []

        def produce(ctx):
            calls.append("produce")
            return StepResult(output={"items": [1]}, variables={"records": [{"value": 1}]})

        flow = AgentFlow(steps=[produce], cache=ReferenceCache())
        result = flow.run("same", verbose=False)
        if boundary == "hit":
            result = flow.run("same", verbose=False)
        if field == "output":
            result["output"]["items"].append(999)
        elif field == "variables":
            result["variables"]["records"][0]["value"] = 999
        else:
            result["steps"][0]["status"] = "corrupted"
        later = flow.run("same", verbose=False)
        assert later["output"] == {"items": [1]}
        assert later["variables"]["records"] == [{"value": 1}]
        assert later["steps"][0]["status"] == "completed"
        assert calls == ["produce"]

    def test_uncopyable_handler_variables_are_not_cached_by_reference(self):
        import threading

        calls = []

        def produce(ctx):
            calls.append("produce")
            return StepResult(
                output="ready", variables={"lock": threading.Lock(), "items": [1]}
            )

        flow = AgentFlow(steps=[produce], cache=True)
        first = flow.run("same", verbose=False)
        first["variables"]["items"].append(999)
        second = flow.run("same", verbose=False)
        assert second["variables"]["items"] == [1]
        assert calls == ["produce", "produce"]

    @pytest.mark.parametrize("boundary", ["miss", "hit"])
    def test_nested_reference_cache_snapshots_variables(self, boundary):
        class ReferenceCache:
            def __init__(self):
                self.entries = {}

            def get(self, key):
                return self.entries.get(key)

            def set(self, key, value):
                self.entries[key] = value

        calls = []

        def produce(ctx):
            calls.append("produce")
            return StepResult(output="ready", variables={"records": [{"value": 1}]})

        flow = AgentFlow(steps=[Parallel(steps=[produce])], cache=ReferenceCache())
        result = flow.run("same", verbose=False)
        if boundary == "hit":
            result = flow.run("same", verbose=False)
        result["variables"]["records"][0]["value"] = 999
        assert flow.run("same", verbose=False)["variables"]["records"] == [{"value": 1}]
        assert calls == ["produce"]

    def test_custom_cache_rejecting_variables_does_not_abort_workflow(self):
        import json
        import threading

        class JsonCache:
            def get(self, key):
                return None

            def set(self, key, value):
                json.dumps(value)

        def produce(ctx):
            return StepResult(output="ready", variables={"lock": threading.Lock()})

        flow = AgentFlow(steps=[produce], cache=JsonCache())
        result = flow.run("same", verbose=False)
        assert result["output"] == "ready"
        assert "lock" in result["variables"]
        assert result["steps"][0]["status"] == "completed"

    def test_legacy_cache_entry_restores_output_variable_and_status(self):
        cache = InMemoryStepCache()
        cache.set(make_step_key("upstream", None, "same", {"input": "same"}), {
            "output": "cached", "variables": {"upstream_output": "cached"},
        })
        calls = []
        flow = AgentFlow(steps=[_counting_step("upstream", calls)], cache=cache)
        result = flow.run("same", verbose=False)
        assert calls == []
        assert result["output"] == "cached"
        assert result["variables"]["upstream_output"] == "cached"
        assert result["steps"] == [{
            "step": "upstream", "output": "cached", "status": "completed", "retries": 0,
        }]
        assert flow.step_statuses["upstream"] == "completed"

    def test_a_cache_hit_preserves_early_stop(self):
        calls = []

        def finish(ctx):
            calls.append("finish")
            return StepResult(
                output="done", stop_workflow=True, variables={"finished": True}
            )

        def downstream(ctx):
            calls.append("downstream")
            return "unexpected"

        flow = AgentFlow(steps=[finish, downstream], cache=True)
        first = flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)

        assert calls == ["finish"]
        assert second == first
        assert "finish_output" not in second["variables"]

    def test_a_cache_hit_restores_handler_variables_for_downstream(self):
        calls = []

        def produce(ctx):
            calls.append("produce")
            return StepResult(output="ready", variables={"answer": 42})

        def consume(ctx):
            calls.append("consume")
            return str(ctx.variables.get("answer", "missing"))

        flow = AgentFlow(steps=[produce, consume], cache=True)
        first = flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)

        assert first["output"] == second["output"] == "42"
        assert second["variables"]["answer"] == 42
        assert calls == ["produce", "consume"]

    def test_a_cache_hit_reports_completed_step_status(self):
        flow = AgentFlow(steps=[_counting_step("upstream", [])], cache=True)
        first = flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)

        assert second["steps"] == first["steps"]
        assert flow.step_statuses["upstream"] == "completed"

    def test_a_cache_hit_still_exposes_the_step_output_variable(self):
        """A fresh run starts with empty working variables. A hit that restored
        only `output` would leave `<step>_output` missing from the run's
        variable state -- so a downstream substitution would break. The step's
        output variable must be present even on a fully cached re-run."""
        flow = AgentFlow(steps=[_counting_step("upstream", [])], cache=True)
        flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)  # served entirely from cache
        assert second["variables"].get("upstream_output") == "upstream-output"

    def test_a_transient_failure_inside_a_pattern_is_not_cached(self):
        """A nested step that fails once must be free to retry and succeed on
        the next run, not replay a cached failure forever."""
        attempts = {"n": 0}

        def flaky(ctx):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return "recovered"

        flaky.__name__ = "flaky"
        flow = AgentFlow(steps=[Parallel(steps=[flaky])], cache=True)
        flow.run("same", verbose=False)   # first attempt fails
        flow.run("same", verbose=False)   # must retry, not serve cached failure
        assert attempts["n"] == 2

    def test_a_cached_stop_still_stops_the_workflow(self):
        """A handler that stopped the cold run must also stop the cached run.
        Losing the stop flag on a hit ran downstream steps that the cold run
        never reached."""
        calls = []

        def finish(ctx):
            calls.append("finish")
            return StepResult(output="done", stop_workflow=True)

        finish.__name__ = "finish"

        def downstream(ctx):
            calls.append("downstream")
            return "unexpected"

        downstream.__name__ = "downstream"

        flow = AgentFlow(steps=[finish, downstream], cache=True)
        flow.run("same", verbose=False)
        flow.run("same", verbose=False)
        assert calls == ["finish"]

    def test_a_cached_hit_preserves_handler_variables(self):
        """A producer returning variables followed by a consumer reading them
        must give the same output on the cached run as the cold one."""
        def producer(ctx):
            return StepResult(output="p", variables={"answer": 42})

        producer.__name__ = "producer"

        def consumer(ctx):
            return f"answer={ctx.variables.get('answer')}"

        consumer.__name__ = "consumer"

        flow = AgentFlow(steps=[producer, consumer], cache=True)
        first = flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)
        assert first["output"] == "answer=42"
        assert second["output"] == first["output"]

    def test_a_cached_hit_preserves_completion_metadata(self):
        """Step status and retries must survive a cache hit, not disappear from
        the result records."""
        flow = AgentFlow(steps=[_counting_step("s", [])], cache=True)
        flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)
        record = second["steps"][0]
        assert record["status"] == "completed"
        assert record["retries"] == 0

    def test_an_early_stop_hit_does_not_insert_the_output_variable(self):
        """The cold path stops before writing `<step>_output`; a cached early
        stop must not insert it either."""
        def finish(ctx):
            return StepResult(output="done", stop_workflow=True)

        finish.__name__ = "finish"

        flow = AgentFlow(steps=[finish], cache=True)
        flow.run("same", verbose=False)
        second = flow.run("same", verbose=False)
        assert "finish_output" not in second["variables"]

    def test_a_mutated_hit_does_not_corrupt_the_cache(self):
        """Values handed back on a hit are snapshots; mutating one must not
        change what the next hit returns."""
        cache = InMemoryStepCache()
        cache.set("k", {"output": "v", "variables": {"a": 1}})
        first = cache.get("k")
        first["variables"]["a"] = 999
        first["output"] = "tampered"
        second = cache.get("k")
        assert second["variables"]["a"] == 1
        assert second["output"] == "v"


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

    def test_a_variable_value_keeps_its_type_in_the_key(self):
        """True and the string "True" are different calls; collapsing both to
        "True" would serve one's answer to the other."""
        a = make_step_key("s", None, "in", {"flag": True})
        b = make_step_key("s", None, "in", {"flag": "True"})
        assert a != b


class TestTheCacheItself:
    def test_uncopyable_replacement_removes_the_old_entry(self):
        import threading

        cache = InMemoryStepCache()
        cache.set("k", {"output": "old"})
        cache.set("k", {"output": "new", "lock": threading.Lock()})
        assert cache.get("k") is None

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
