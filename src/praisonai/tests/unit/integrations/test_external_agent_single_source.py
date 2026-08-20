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
    """Register a plugin in a throwaway registry and make it the default."""
    reg = registry_mod.ExternalAgentRegistry()
    reg.register("aider", AiderIntegration)
    monkeypatch.setattr(registry_mod, "_default_registry", reg)
    return reg


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


def test_registry_does_not_configure_the_root_logger(broken_plugin):
    import logging

    logging.getLogger().handlers.clear()
    registry_mod.external_agent_catalog()
    assert logging.getLogger().handlers == []
