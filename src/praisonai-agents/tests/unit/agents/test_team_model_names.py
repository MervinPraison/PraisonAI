"""D-10: AgentTeam follows Agent's model naming.

``Agent(llm=)`` warns that ``llm=`` is a deprecated alias of ``model=``;
``AgentTeam(llm=)`` accepted the same alias silently. And ``manager_llm=`` had
no ``manager_model=`` spelling to match ``model=``.
"""

import warnings

import pytest

from praisonaiagents import Agent, AgentTeam
from praisonaiagents.utils import deprecation


@pytest.fixture
def fresh_warnings(monkeypatch):
    # The deprecation helper warns once per process; start from a clean set.
    monkeypatch.setattr(deprecation, "_warned_params", set())


def _member():
    return Agent(name="m", instructions="bot", model="gpt-4o-mini")


def test_team_llm_alias_warns_at_the_caller(fresh_warnings):
    with pytest.warns(DeprecationWarning, match="'llm' is deprecated") as record:
        team = AgentTeam(agents=[_member()], llm="gpt-4o-mini")
    assert team.llm == "gpt-4o-mini"
    assert record[0].filename == __file__


def test_team_model_does_not_warn(fresh_warnings):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        AgentTeam(agents=[_member()], model="gpt-4o-mini")


def test_manager_model_is_an_alias_of_manager_llm():
    team = AgentTeam(agents=[_member()], manager_model="gpt-4o")
    assert team.manager_llm == "gpt-4o"


def test_manager_llm_and_manager_model_together_are_refused():
    with pytest.raises(TypeError, match="manager_model"):
        AgentTeam(agents=[_member()], manager_llm="a", manager_model="b")
