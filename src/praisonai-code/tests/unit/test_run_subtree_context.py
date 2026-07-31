"""Tests for wiring the subtree instruction hook into ``praisonai run``.

The interactive REPL lazily attaches a subdirectory's ``AGENTS.md`` the first
time the agent reads/edits a file under it. These tests cover the equivalent
wiring for the scriptable ``praisonai run`` path (`_wire_subtree_context_hook`)
so a monorepo run picks up ``packages/foo/AGENTS.md`` exactly like ``chat``.
"""

from types import SimpleNamespace

import pytest

from praisonai_code.cli.commands.run import _wire_subtree_context_hook


@pytest.fixture
def monorepo(tmp_path, monkeypatch):
    """A monorepo with a root and a nested package, with a fake git root."""
    root = tmp_path / "repo"
    foo = root / "packages" / "foo"
    foo.mkdir(parents=True)
    (root / "AGENTS.md").write_text("ROOT RULES")
    (foo / "AGENTS.md").write_text("FOO RULES")
    # Force deterministic git-root detection to the repo root.
    monkeypatch.setattr(
        "praisonai_bot.integration.context_files._get_git_root",
        lambda start: root,
    )
    return root, foo


def _fire_after_tool(registry, tool_input):
    """Invoke every AFTER_TOOL function hook and return their contexts."""
    from praisonaiagents.hooks import HookEvent

    event = SimpleNamespace(tool_input=tool_input)
    contexts = []
    for hook in registry.get_hooks(HookEvent.AFTER_TOOL):
        func = getattr(hook, "func", hook)
        result = func(event)
        if result is not None and getattr(result, "additional_context", None):
            contexts.append(result.additional_context)
    return "\n".join(contexts)


def test_run_wiring_attaches_subtree_rules(monorepo):
    _root, foo = monorepo
    agent_config = {"name": "RunAgent"}

    _wire_subtree_context_hook(agent_config)

    registry = agent_config.get("hooks")
    assert registry is not None, "subtree hook should be registered by default"

    context = _fire_after_tool(registry, {"file_path": str(foo / "bar.py")})
    assert "FOO RULES" in context


def test_run_wiring_noop_with_no_rules(monorepo):
    _root, foo = monorepo
    agent_config = {"name": "RunAgent"}

    _wire_subtree_context_hook(agent_config, no_rules=True)

    assert "hooks" not in agent_config


def test_run_wiring_noop_with_env_off_switch(monorepo, monkeypatch):
    _root, foo = monorepo
    monkeypatch.setenv("PRAISON_NO_RULES", "true")
    agent_config = {"name": "RunAgent"}

    _wire_subtree_context_hook(agent_config)

    assert "hooks" not in agent_config
