"""Every --external-agent surface must read the registry, not a local copy."""

import argparse

import pytest

from praisonai.integrations.base import BaseCLIIntegration
from praisonai.integrations import registry as registry_mod

BUILTINS = ["claude", "gemini", "codex", "cursor"]


class AiderIntegration(BaseCLIIntegration):
    display_label = "Aider (test plugin)"
    install_hint = "pip install aider-chat"

    @property
    def cli_command(self) -> str:
        return "aider"

    async def execute(self, prompt: str, **options) -> str:  # pragma: no cover
        return prompt

    async def stream(self, prompt: str, **options):  # pragma: no cover
        yield prompt


@pytest.fixture
def registered_plugin(monkeypatch):
    """Register a plugin in a throwaway registry and make it the default.

    Every external-agent surface reads the *process-default* registry, some
    directly (``registry_mod._default_registry``) and some through the
    ``praisonai-code`` handler bridge, which resolves the registry lazily. To
    make the fixture immune to test ordering under ``pytest -n --dist loadfile``
    (where hundreds of files share one worker), we also clear the per-class
    ``PluginRegistry.default()`` cache so no sibling test's cached instance can
    shadow ours, and restore it afterwards.
    """
    cls = registry_mod.ExternalAgentRegistry
    saved_default = cls.__dict__.get("_default_instance")
    if "_default_instance" in cls.__dict__:
        delattr(cls, "_default_instance")

    reg = cls()
    reg.register("aider", AiderIntegration)
    monkeypatch.setattr(registry_mod, "_default_registry", reg)
    setattr(cls, "_default_instance", reg)
    try:
        yield reg
    finally:
        if saved_default is not None:
            setattr(cls, "_default_instance", saved_default)
        elif "_default_instance" in cls.__dict__:
            delattr(cls, "_default_instance")


def test_registry_lists_the_plugin_after_the_builtins(registered_plugin):
    assert registry_mod.list_external_agents() == BUILTINS + ["aider"]


def test_cli_handler_reads_the_registry(registered_plugin):
    from praisonai.cli.features.external_agents import ExternalAgentsHandler

    handler = ExternalAgentsHandler()
    assert handler.list_integrations() == BUILTINS + ["aider"]
    assert "aider" in handler.INTEGRATIONS
    assert isinstance(handler.get_integration("aider"), AiderIntegration)
    assert "aider" in handler.flag_help
    assert handler._get_install_instructions("aider") == "pip install aider-chat"
    assert (
        handler._get_install_instructions("claude")
        == "npm install -g @anthropic-ai/claude-code"
    )


def test_argparse_choices_accept_the_plugin(registered_plugin, monkeypatch):
    from praisonai.cli.legacy.dispatch import argparse_builder

    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_known_args",
        lambda self, *a, **k: (argparse.Namespace(), []),
    )
    captured = {}
    original_add = argparse._ActionsContainer.add_argument

    def spy(self, *args, **kwargs):
        action = original_add(self, *args, **kwargs)
        if "--external-agent" in args:
            captured["choices"] = kwargs.get("choices")
        return action

    monkeypatch.setattr(argparse._ActionsContainer, "add_argument", spy)
    argparse_builder.build_argument_parser(True)
    assert captured["choices"] == BUILTINS + ["aider"]


def test_ui_toggles_read_the_registry(registered_plugin):
    from praisonai.ui import _external_agents as ui

    assert list(ui.EXTERNAL_AGENTS) == [f"{n}_enabled" for n in BUILTINS + ["aider"]]
    assert ui.EXTERNAL_AGENTS["aider_enabled"]["cli"] == "aider"
    assert ui.EXTERNAL_AGENTS["aider_enabled"]["label"] == "Aider (test plugin)"
    # built-in presentation is unchanged
    assert ui.EXTERNAL_AGENTS["claude_enabled"]["label"] == "Claude Code (coding, file edits)"
    assert ui.EXTERNAL_AGENTS["cursor_enabled"]["cli"] == "cursor-agent"


def test_builtin_is_not_hijacked_by_an_entry_point(monkeypatch):
    """A plugin may add an external agent; it may never replace a shipped one.

    This exercises the real discovery path: the base ``PluginRegistry`` guards
    the collision once (#4171), so a third-party entry point declaring the
    built-in name ``claude`` is skipped while a novel ``aider`` is still added.
    """
    import types

    class Shadow:
        pass

    def fake_entry_points(*args, **kwargs):
        # A plugin collides with a built-in and adds a brand-new name.
        # Accept ``group`` positionally or by keyword so we match the base
        # registry's ``entry_points(group=...)`` call regardless of Python
        # version.
        return [
            types.SimpleNamespace(name="claude", load=lambda: Shadow),
            types.SimpleNamespace(name="aider", load=lambda: AiderIntegration),
        ]

    real = registry_mod.ExternalAgentRegistry()._loaders["claude"]
    # Patch ``entry_points`` on the exact module the ``ExternalAgentRegistry``
    # class discovers through. Using the class's defining module (rather than a
    # re-imported ``praisonai_code._registry`` name) makes this immune to any
    # duplicate-module identity that editable installs + coverage can create on
    # CI, where a re-imported copy would leave the real discovery path unpatched
    # and silently drop the ``aider`` plugin.
    import sys

    base_module = sys.modules[registry_mod.ExternalAgentRegistry.__mro__[1].__module__]
    monkeypatch.setattr(base_module, "entry_points", fake_entry_points)
    reg = registry_mod.ExternalAgentRegistry()
    # Collision: the shipped built-in wins.
    assert reg.resolve("claude") is not Shadow
    assert reg._loaders["claude"] is real
    # New name: the plugin is still added.
    assert reg.resolve("aider") is AiderIntegration


def test_every_surface_agrees(registered_plugin):
    from praisonai.cli.features.external_agents import ExternalAgentsHandler
    from praisonai.ui import _external_agents as ui

    expected = set(BUILTINS) | {"aider"}
    assert set(registry_mod.list_external_agents()) == expected
    assert set(ExternalAgentsHandler().list_integrations()) == expected
    assert {t.removesuffix("_enabled") for t in ui.EXTERNAL_AGENTS} == expected


@pytest.fixture
def broken_plugin(monkeypatch):
    """Register a plugin whose class fails to resolve (loader raises on import)."""
    reg = registry_mod.ExternalAgentRegistry()

    def _raise():
        raise ImportError("broken optional plugin")

    reg._loaders["broken"] = _raise
    monkeypatch.setattr(registry_mod, "_default_registry", reg)
    return reg


def test_argparse_choices_and_the_handler_agree_about_a_broken_plugin(broken_plugin):
    """A name offered in --help must be usable, or the failure must name the real cause."""
    from praisonai.integrations.registry import (
        list_external_agents,
        external_agent_catalog,
    )

    assert set(list_external_agents()) == set(external_agent_catalog())
    assert "broken" not in list_external_agents()


def test_registry_does_not_configure_the_root_logger(broken_plugin, monkeypatch):
    import logging

    # Replace (not permanently clear) the process-global root logger handlers so
    # later tests keep their logging/capture handlers. monkeypatch restores the
    # original list on teardown.
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [])
    registry_mod.external_agent_catalog()
    assert root_logger.handlers == []
