"""D-09: AgentFlow's private and runtime-state fields are not constructor arguments.

AgentFlow(steps=[], _run_lock='oops', status='banana') used to construct. The
underscore fields are resolved in __post_init__ and status/step_statuses are
run state; no caller in the repo passes them. history= stays: it is a user
switch (examples, tests and the YAML parser pass it).
"""

import dataclasses

import pytest

from praisonaiagents import AgentFlow

STATE = {"status", "step_statuses"}


def _private_or_state():
    return [f for f in dataclasses.fields(AgentFlow) if f.name.startswith("_") or f.name in STATE]


def test_private_and_state_fields_are_not_init_parameters():
    open_ = [f.name for f in _private_or_state() if f.init]
    assert open_ == []


@pytest.mark.parametrize("name", ["_run_lock", "status", "step_statuses", "_verbose"])
def test_passing_one_raises(name):
    with pytest.raises(TypeError):
        AgentFlow(steps=[], **{name: "x"})


def test_defaults_unchanged_and_history_still_accepted():
    flow = AgentFlow(steps=[], history=True)
    assert flow.history is True
    assert flow.status == "not_started" and flow.step_statuses == {}
    assert flow._execution_history == [] and flow._handoff_chain == []
