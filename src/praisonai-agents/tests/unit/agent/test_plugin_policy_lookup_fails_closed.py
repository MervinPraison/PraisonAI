"""T-12: a plugin policy must never replace a user policy of the same name.
If looking the name up raises, the plugin rule is skipped (fail closed)
instead of being added, which would overwrite the user's policy.
"""
import logging
import types

import pytest

import praisonaiagents.plugins as plugins_pkg
import praisonaiagents.plugins.manager as manager_mod
from praisonaiagents import Agent


class _Engine:
    def __init__(self, lookup_fails):
        self.lookup_fails = lookup_fails
        self.added = []

    def get_policy(self, name):
        if self.lookup_fails:
            raise RuntimeError("policy store unavailable")
        return None

    def add_policy(self, rule):
        self.added.append(rule.name)


@pytest.fixture
def agent_with_plugin_policy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    rule = types.SimpleNamespace(name="no-shell")
    manager = types.SimpleNamespace(get_all_policies=lambda: [rule])
    monkeypatch.setattr(manager_mod, "has_registered_plugins", lambda: True)
    monkeypatch.setattr(plugins_pkg, "get_plugin_manager", lambda: manager)
    return Agent(name="a", instructions="hi")


def test_failed_lookup_skips_the_plugin_rule(agent_with_plugin_policy, caplog):
    agent = agent_with_plugin_policy
    agent._policy = engine = _Engine(lookup_fails=True)
    with caplog.at_level(logging.WARNING):
        agent._merge_plugin_subsystems()
    assert engine.added == []
    assert any("could not check" in r.getMessage() for r in caplog.records)


def test_rule_is_added_when_no_policy_has_its_name(agent_with_plugin_policy):
    agent = agent_with_plugin_policy
    agent._policy = engine = _Engine(lookup_fails=False)
    agent._merge_plugin_subsystems()
    assert engine.added == ["no-shell"]
