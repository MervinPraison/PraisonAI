"""Every documented back-compat alias must import from the package root.

`PraisonAIAgents` was exported from praisonaiagents.agents but omitted from the
root lazy-import map, so `from praisonaiagents import PraisonAIAgents` raised
ImportError while the submodule import worked. That silently disabled all AI
features in praisonaiwp, which guards on exactly this import.
"""
import importlib

import pytest

ALIASES = ["AgentTeam", "AgentManager", "Agents", "PraisonAIAgents"]


@pytest.mark.parametrize("name", ALIASES)
def test_alias_importable_from_package_root(name):
    mod = importlib.import_module("praisonaiagents")
    assert hasattr(mod, name), f"{name} is not importable from praisonaiagents"


@pytest.mark.parametrize("name", ALIASES)
def test_alias_in_dunder_all(name):
    mod = importlib.import_module("praisonaiagents")
    assert name in mod.__all__, f"{name} missing from praisonaiagents.__all__"


def test_root_and_submodule_aliases_are_the_same_object():
    from praisonaiagents import PraisonAIAgents as root
    from praisonaiagents.agents import PraisonAIAgents as sub

    assert root is sub


def test_aliases_all_resolve_to_agent_team():
    import praisonaiagents
    from praisonaiagents.agents.agents import AgentTeam

    for name in ALIASES:
        assert getattr(praisonaiagents, name) is AgentTeam, f"{name} != AgentTeam"
