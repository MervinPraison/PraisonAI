"""repeat() accepts a list of steps.

Repeat.step is typed Any and was handed straight to the single-step executor, so
repeat([a, b]) was ACCEPTED and then stringified into a prompt -- the list became
text and the default agent answered it. Since there is no N-agent discussion
loop, that is exactly the workaround people reach for, which made the silent
misbehaviour worse than a rejection would have been.
"""
import pytest

from praisonaiagents.workflows.workflows import AgentFlow, Repeat


def _step(name, log):
    def handler(ctx):
        log.append(name)
        return name.upper()
    handler.__name__ = name
    return handler


class TestAListRuns:
    def test_every_member_runs_in_order_each_iteration(self):
        log = []
        flow = AgentFlow(steps=[Repeat([_step("a", log), _step("b", log)], max_iterations=2)])
        flow.run("go", verbose=False)
        assert log == ["a", "b", "a", "b"]

    def test_the_list_is_not_stringified_into_a_prompt(self):
        """The defect: the list used to reach the model as text."""
        log = []
        flow = AgentFlow(steps=[Repeat([_step("a", log)], max_iterations=1)])
        result = flow.run("go", verbose=False)
        assert "step" not in str(result).lower() or log == ["a"]
        assert log == ["a"]

    def test_each_member_sees_the_previous_members_output(self):
        seen = []

        def first(ctx):
            return "FROM_FIRST"

        def second(ctx):
            seen.append(ctx.previous_result)
            return "done"

        first.__name__, second.__name__ = "first", "second"
        AgentFlow(steps=[Repeat([first, second], max_iterations=1)]).run("go", verbose=False)
        assert seen == ["FROM_FIRST"]


class TestControls:
    def test_control_a_single_step_still_works(self):
        log = []
        AgentFlow(steps=[Repeat(_step("only", log), max_iterations=3)]).run("go", verbose=False)
        assert log == ["only", "only", "only"]

    def test_control_max_iterations_still_bounds_a_list(self):
        log = []
        AgentFlow(steps=[Repeat([_step("a", log), _step("b", log)], max_iterations=3)]).run(
            "go", verbose=False
        )
        assert log == ["a", "b"] * 3

    def test_control_until_still_stops_a_list_early(self):
        log = []
        flow = AgentFlow(steps=[
            Repeat(
                [_step("a", log), _step("b", log)],
                until=lambda ctx: True,
                max_iterations=5,
            )
        ])
        flow.run("go", verbose=False)
        assert log == ["a", "b"]
