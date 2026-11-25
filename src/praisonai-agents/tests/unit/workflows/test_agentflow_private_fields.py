"""D-09: AgentFlow's private (underscore) fields are not constructor arguments.

AgentFlow(steps=[], _run_lock='oops') used to construct. The underscore fields
are resolved in __post_init__; no caller in the repo passes them. status= and
step_statuses= are public names and stay accepted (removing them needs a
deprecation cycle). history= stays: it is a user switch.
"""

import dataclasses

import pytest

from praisonaiagents import AgentFlow

def test_private_fields_are_not_init_parameters():
    open_ = [f.name for f in dataclasses.fields(AgentFlow) if f.name.startswith("_") and f.init]
    assert open_ == []


@pytest.mark.parametrize("name", ["_run_lock", "_verbose", "_execution_history"])
def test_passing_one_raises(name):
    with pytest.raises(TypeError):
        AgentFlow(steps=[], **{name: "x"})


def test_defaults_unchanged_and_public_fields_still_accepted():
    flow = AgentFlow(steps=[], history=True)
    assert flow.history is True
    assert AgentFlow(steps=[], status="running").status == "running"
    assert flow.status == "not_started" and flow.step_statuses == {}
    assert flow._execution_history == [] and flow._handoff_chain == []
