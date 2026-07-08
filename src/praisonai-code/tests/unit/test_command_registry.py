"""Tests for the unified interactive command registry (issue #2791).

Custom ``.praisonai/commands/*.md`` commands must be first-class ``/name``
commands in interactive sessions, resolved from a single registry that also
powers ``/help`` and autocomplete, with full parity to
``praisonai run --command <name>``.
"""

import os
from pathlib import Path

import pytest

from praisonai_code.cli.interactive.command_registry import (
    Command,
    CommandKind,
    CommandRegistry,
    BuiltinCommandSource,
    CustomCommandSource,
    create_default_registry,
)


def _make_project_command(tmp_path: Path, name: str, description: str, body: str) -> None:
    cmd_dir = tmp_path / ".praisonai" / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (cmd_dir / f"{name}.md").write_text(
        f"---\ndescription: {description}\n---\n{body}\n"
    )


def test_builtin_source_yields_commands():
    source = BuiltinCommandSource({"help": "Show help", "exit": "Exit"})
    commands = source.discover()
    names = {c.name for c in commands}
    assert names == {"help", "exit"}
    assert all(c.kind == CommandKind.BUILTIN for c in commands)


def test_registry_later_source_overrides_earlier():
    reg = CommandRegistry(
        sources=[
            BuiltinCommandSource({"dup": "builtin desc"}),
        ],
        discover_entry_points=False,
    )
    reg.add_source(
        _StaticSource([Command(name="dup", description="override", source="project")])
    )
    resolved = reg.get("dup")
    assert resolved is not None
    assert resolved.description == "override"
    assert resolved.source == "project"


def test_registry_lookup_by_alias():
    reg = CommandRegistry(
        sources=[
            _StaticSource(
                [Command(name="quit", description="Exit", aliases=["q", "bye"])]
            )
        ],
        discover_entry_points=False,
    )
    assert reg.get("quit") is not None
    assert reg.get("q") is not None
    assert reg.get("bye") is not None
    assert reg.get("missing") is None


def test_registry_completions():
    reg = CommandRegistry(
        sources=[
            _StaticSource(
                [
                    Command(name="model"),
                    Command(name="multiline"),
                    Command(name="help"),
                ]
            )
        ],
        discover_entry_points=False,
    )
    assert reg.completions("/m") == ["/model", "/multiline"]
    assert reg.completions("no-slash") == []


def test_custom_command_source_discovers_project_commands(tmp_path, monkeypatch):
    _make_project_command(
        tmp_path, "deploy", "Deploy the app", "Deploy with args: $ARGUMENTS"
    )
    monkeypatch.chdir(tmp_path)
    # Isolate user-global dir so a real ~/.praisonai does not leak in.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    source = CustomCommandSource()
    commands = {c.name: c for c in source.discover()}
    assert "deploy" in commands
    deploy = commands["deploy"]
    assert deploy.kind == CommandKind.CUSTOM
    assert deploy.description == "Deploy the app"
    assert deploy.handler is not None


def test_custom_command_handler_matches_run_command_path(tmp_path, monkeypatch):
    """Interactive /name must produce the same text as run --command."""
    _make_project_command(
        tmp_path, "greet", "Greet", "Hello $ARGUMENTS from the template"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    reg = create_default_registry(
        {"help": "Show help"}, include_custom=True, discover_entry_points=False
    )
    cmd = reg.get("greet")
    assert cmd is not None
    interactive_output = cmd.handler("World")

    from praisonai_code.cli.features.custom_definitions import (
        interpolate_command_template,
    )

    cli_output = interpolate_command_template("greet", "World")
    assert interactive_output == cli_output
    assert "Hello World from the template" in interactive_output


def test_default_registry_merges_builtins_and_custom(tmp_path, monkeypatch):
    _make_project_command(tmp_path, "mydeploy", "My deploy", "do it")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    reg = create_default_registry(
        {"help": "Show help", "exit": "Exit"},
        include_custom=True,
        discover_entry_points=False,
    )
    names = set(reg.names())
    assert {"help", "exit", "mydeploy"} <= names
    assert reg.has("mydeploy")
    assert reg.get("mydeploy").kind == CommandKind.CUSTOM


def test_builtin_not_shadowed_by_custom_command():
    """A custom command reusing a built-in name must not shadow the built-in.

    Built-ins are dispatched by the interactive surface *before* the registry
    is consulted, so a shadowing custom entry would never execute. The registry
    keeps the built-in so listing matches runtime behaviour.
    """
    reg = CommandRegistry(
        sources=[
            BuiltinCommandSource({"exit": "Exit interactive mode"}),
            _StaticSource(
                [
                    Command(
                        name="exit",
                        description="custom exit",
                        kind=CommandKind.CUSTOM,
                        source="project",
                    )
                ]
            ),
        ],
        discover_entry_points=False,
    )
    resolved = reg.get("exit")
    assert resolved is not None
    assert resolved.kind is CommandKind.BUILTIN
    assert resolved.description == "Exit interactive mode"


def test_registry_survives_failing_source():
    reg = CommandRegistry(
        sources=[_FailingSource(), _StaticSource([Command(name="ok")])],
        discover_entry_points=False,
    )
    # A broken source must not take down the registry.
    assert reg.has("ok")


class _StaticSource:
    def __init__(self, commands):
        self._commands = commands

    def discover(self):
        return list(self._commands)


class _FailingSource:
    def discover(self):
        raise RuntimeError("boom")
