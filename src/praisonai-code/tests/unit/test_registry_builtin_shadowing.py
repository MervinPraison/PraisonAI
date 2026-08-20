"""A third-party entry point may add names to a registry; it may never replace
a shipped built-in (issue #4171).

#4158 patched ``ExternalAgentRegistry`` alone. The hole was in the base
``PluginRegistry``: builtins are registered first, entry points second, and the
last write won -- so any installed distribution declaring a built-in name
(``openai`` in ``praisonai.llm_providers``, ``docker`` in ``praisonai.sandbox``,
``aws`` in ``praisonai.deploy.providers`` ...) took over that name on every
surface. Those loaders decide *where user code runs*.

The fix guards discovery once, in the base class: an entry point whose name
matches a built-in is skipped and the built-in kept. Runtime ``register()``
still overrides -- that is deliberate dependency injection.
"""

import contextlib
import types

import pytest

from praisonai_code._registry import PluginRegistry


class _Builtin:
    """Shipped loader we must never lose to a plugin of the same name."""


class _Evil:
    """A third-party distribution's replacement for a built-in name."""


def _entry_point(name, obj):
    """A stand-in for importlib.metadata.EntryPoint with the two attributes the
    registry uses: ``.name`` and ``.load()``."""
    return types.SimpleNamespace(name=name, load=lambda: obj)


@pytest.mark.parametrize(
    "group,builtin",
    [
        ("praisonai.llm_providers", "openai"),
        ("praisonai.sandbox", "docker"),
        ("praisonai.managed_backends", "docker"),
        ("praisonai.deploy.providers", "aws"),
    ],
)
def test_entry_point_cannot_replace_a_builtin(monkeypatch, group, builtin):
    monkeypatch.setattr(
        "praisonai_code._registry.entry_points",
        lambda group: [_entry_point(builtin, _Evil)],
    )

    registry = PluginRegistry(
        entry_point_group=group,
        builtins={builtin: lambda: _Builtin},
    )

    assert registry.resolve(builtin) is _Builtin


def test_entry_point_may_still_add_a_new_name(monkeypatch):
    """Additive plugins are unaffected: a novel name still resolves."""
    monkeypatch.setattr(
        "praisonai_code._registry.entry_points",
        lambda group: [_entry_point("thirdparty", _Evil)],
    )

    registry = PluginRegistry(
        entry_point_group="praisonai.sandbox",
        builtins={"docker": lambda: _Builtin},
    )

    assert registry.resolve("docker") is _Builtin
    assert registry.resolve("thirdparty") is _Evil
    assert "thirdparty" in registry.list_names()


def test_runtime_register_still_overrides_a_builtin():
    """Explicit ``register()`` is deliberate DI and must still win."""
    registry = PluginRegistry(
        entry_point_group="praisonai.sandbox",
        builtins={"docker": lambda: _Builtin},
        discover_entry_points=False,
    )

    registry.register("docker", _Evil)

    assert registry.resolve("docker") is _Evil


def test_builtin_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(
        "praisonai_code._registry.entry_points",
        lambda group: [_entry_point("OpenAI", _Evil)],
    )

    registry = PluginRegistry(
        entry_point_group="praisonai.llm_providers",
        builtins={"openai": lambda: _Builtin},
    )

    assert registry.resolve("openai") is _Builtin


@pytest.mark.parametrize("group_kind", ["canonical", "legacy"])
def test_neither_group_lets_an_entry_point_replace_a_builtin(monkeypatch, group_kind):
    """The deprecated spelling must not be a way around the built-in guard --
    it is discovered first, so an unguarded legacy pass would win outright
    (issue #4183)."""
    canonical = "praisonai.sandbox"
    legacy = "praisonai.sandbox.legacy"
    target = legacy if group_kind == "legacy" else canonical

    monkeypatch.setattr(
        "praisonai_code._registry.entry_points",
        lambda group: [_entry_point("docker", _Evil)] if group == target else [],
    )

    expect = (
        pytest.warns(DeprecationWarning)
        if group_kind == "legacy"
        else contextlib.nullcontext()
    )
    with expect:
        registry = PluginRegistry(
            entry_point_group=canonical,
            builtins={"docker": lambda: _Builtin},
            legacy_entry_point_groups=(legacy,),
        )

    assert registry.resolve("docker") is _Builtin
