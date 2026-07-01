"""Tests for ToolSourceRegistry entry-point extensibility (issue #2510, Gap 3).

Verifies tool sources are a first-class, entry-point-pluggable extension surface
that mirrors the other PluginRegistry-based registries, and that ToolResolver
consumes them without breaking the built-in resolution chain.
"""

import pytest

from praisonai.tool_resolver import (
    ToolResolver,
    ToolSource,
    ToolSourceRegistry,
    _ResolveResult,
)


class _FakeSource:
    """A ready-made ToolSource instance."""

    name = "fake"

    def __init__(self):
        self._tool = lambda: "fake-result"

    def lookup(self, name):
        if name == "fake_tool":
            return _ResolveResult(self._tool)
        return None


class _FactorySource:
    """A ToolSource returned from a zero-arg factory/class."""

    name = "factory"

    def lookup(self, name):
        return (lambda: "factory-result") if name == "factory_tool" else None


def test_registry_mirrors_plugin_registry_shape():
    # discover_entry_points=False isolates the registry from whatever
    # praisonai.tool_sources plugins happen to be installed in the environment,
    # keeping the empty-registry assertions deterministic.
    reg = ToolSourceRegistry(discover_entry_points=False)
    assert reg.list_names() == []
    assert reg.create_sources() == []


def test_registry_instantiates_factory_sources():
    reg = ToolSourceRegistry(discover_entry_points=False)
    reg.register("factory", _FactorySource)
    sources = reg.create_sources()
    assert len(sources) == 1
    assert sources[0].name == "factory"
    assert sources[0].lookup("factory_tool")() == "factory-result"


def test_registry_uses_ready_made_instances():
    reg = ToolSourceRegistry(discover_entry_points=False)
    instance = _FakeSource()
    reg.register("fake", lambda: instance)
    sources = reg.create_sources()
    assert sources[0] is instance


def test_resolver_appends_entry_point_sources():
    reg = ToolSourceRegistry(discover_entry_points=False)
    reg.register("fake", _FakeSource)
    resolver = ToolResolver(source_registry=reg)
    # Built-in chain (5) plus the one entry-point source.
    names = [getattr(s, "name", None) for s in resolver._sources]
    assert names[:5] == [
        "local-tools.py",
        "wrapper-registry",
        "praisonaiagents",
        "praisonai-tools",
        "core-registry",
    ]
    assert "fake" in names
    # The entry-point source actually resolves.
    assert resolver.resolve("fake_tool")() == "fake-result"


def test_empty_registry_opts_out():
    resolver = ToolResolver(
        source_registry=ToolSourceRegistry(discover_entry_points=False)
    )
    names = [getattr(s, "name", None) for s in resolver._sources]
    assert "fake" not in names
    assert len(resolver._sources) == 5


def test_explicit_sources_bypass_registry():
    reg = ToolSourceRegistry(discover_entry_points=False)
    reg.register("fake", _FakeSource)
    # sources= fully controls the chain; entry-point sources are NOT appended.
    resolver = ToolResolver(sources=[_FakeSource()], source_registry=reg)
    assert len(resolver._sources) == 1
    assert resolver._sources[0].name == "fake"


def test_misbehaving_plugin_is_skipped():
    reg = ToolSourceRegistry(discover_entry_points=False)

    def _boom():
        raise RuntimeError("bad plugin")

    reg.register("boom", _boom)
    reg.register("factory", _FactorySource)
    # The bad plugin is skipped, the good one survives.
    sources = reg.create_sources()
    assert [s.name for s in sources] == ["factory"]


def test_invalid_shape_plugin_is_skipped():
    # A plugin that resolves to something that is NOT a ToolSource (e.g. a
    # plain string / object without a callable lookup) must be rejected during
    # loading rather than appended to the chain, where every lookup would raise.
    reg = ToolSourceRegistry(discover_entry_points=False)
    reg.register("bad", lambda: "not-a-tool-source")
    reg.register("factory", _FactorySource)
    sources = reg.create_sources()
    assert [s.name for s in sources] == ["factory"]
