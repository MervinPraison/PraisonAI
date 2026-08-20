"""Third-party ``praisonai.integrations`` entry points must survive construction.

``IntegrationRegistry.__init__`` used to reassign ``self._loaders = {}`` right
after ``super().__init__()`` had populated it from the entry-point group, which
threw away every discovered plugin.
"""

from importlib.metadata import EntryPoint

import pytest

import praisonai_code._registry as base_registry
from praisonai.integrations._unified_registry import IntegrationRegistry


class _AcmeIntegration:
    """Stand-in for a third-party integration class."""


@pytest.fixture
def acme_entry_point(monkeypatch):
    ep = EntryPoint(
        name="acme",
        value="tests.unit.integrations.test_unified_registry_entry_points:_AcmeIntegration",
        group="praisonai.integrations",
    )
    monkeypatch.setattr(ep.__class__, "load", lambda self: _AcmeIntegration, raising=False)

    def fake_entry_points(*, group):
        return [ep] if group == "praisonai.integrations" else []

    monkeypatch.setattr(base_registry, "entry_points", fake_entry_points)
    return ep


def test_entry_point_plugin_is_listed(acme_entry_point):
    registry = IntegrationRegistry()
    assert "acme" in registry.list_names()


def test_entry_point_plugin_resolves(acme_entry_point):
    registry = IntegrationRegistry()
    assert registry.resolve("acme") is _AcmeIntegration


def test_builtins_are_still_registered(acme_entry_point):
    registry = IntegrationRegistry()
    names = registry.list_names()
    for builtin in (
        "claudecodeintegration",
        "geminicliintegration",
        "codexcliintegration",
        "cursorcliintegration",
        "basecliintegration",
        "create_integration",
    ):
        assert builtin in names, builtin
    assert registry.resolve("ClaudeCodeIntegration").__name__ == "ClaudeCodeIntegration"


def test_builtin_aliases_are_still_registered(acme_entry_point):
    registry = IntegrationRegistry()
    aliases = registry.list_aliases()
    assert aliases["managedagentintegration"] == "managedagent"
    assert aliases["managedbackendconfig"] == "managedconfig"


def test_builtin_wins_over_same_named_plugin(monkeypatch):
    """A plugin may not silently replace a built-in integration."""
    ep = EntryPoint(
        name="ClaudeCodeIntegration",
        value="x:y",
        group="praisonai.integrations",
    )
    monkeypatch.setattr(ep.__class__, "load", lambda self: _AcmeIntegration, raising=False)
    monkeypatch.setattr(
        base_registry,
        "entry_points",
        lambda *, group: [ep] if group == "praisonai.integrations" else [],
    )
    registry = IntegrationRegistry()
    assert registry.resolve("ClaudeCodeIntegration").__name__ == "ClaudeCodeIntegration"
