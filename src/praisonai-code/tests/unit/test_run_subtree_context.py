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


def _param_default(func, name):
    import inspect

    return inspect.signature(func).parameters[name].default


def test_custom_agent_and_profiled_forward_no_rules():
    """``--no-rules`` must reach the subtree hook on every non-interactive path.

    ``_run_prompt`` already forwarded ``no_rules``; the custom-agent and
    profiled paths dropped it, so ``praisonai run --no-rules --agent ...`` /
    ``--profile`` still injected subtree rules. Guard that both now accept and
    default ``no_rules`` so the opt-out propagates.
    """
    from praisonai_code.cli.commands.run import (
        _run_custom_agent,
        _run_prompt,
        _run_prompt_profiled,
    )

    for fn in (_run_prompt, _run_custom_agent, _run_prompt_profiled):
        assert _param_default(fn, "no_rules") is False


# --- Config-declared instruction sources (--instructions / config) ---------


def test_wiring_injects_instruction_sources_up_front(tmp_path, monkeypatch):
    """Config/flag instruction sources land in the agent backstory up front."""
    monkeypatch.setattr(
        "praisonai_bot.integration.context_files._get_git_root",
        lambda start: tmp_path,
    )
    rules = tmp_path / "standards.md"
    rules.write_text("ORG STANDARD")

    agent_config = {"name": "RunAgent"}
    _wire_subtree_context_hook(agent_config, instructions=[str(rules)])

    backstory = agent_config.get("backstory") or ""
    assert "ORG STANDARD" in backstory
    assert "# Project Instructions" in backstory


def test_wiring_no_instructions_leaves_backstory_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "praisonai_bot.integration.context_files._get_git_root",
        lambda start: tmp_path,
    )
    agent_config = {"name": "RunAgent", "backstory": "BASE"}
    _wire_subtree_context_hook(agent_config, instructions=None)
    assert agent_config["backstory"] == "BASE"


def test_wiring_no_rules_skips_instruction_injection(tmp_path):
    rules = tmp_path / "standards.md"
    rules.write_text("ORG STANDARD")
    agent_config = {"name": "RunAgent"}
    _wire_subtree_context_hook(
        agent_config, no_rules=True, instructions=[str(rules)]
    )
    assert "backstory" not in agent_config


def test_merge_instructions_layers_config_then_cli(tmp_path, monkeypatch):
    """Config-declared sources come first; --instructions merge on top."""
    from praisonai_code.cli.commands import run as run_mod

    monkeypatch.setattr(
        run_mod, "_resolve_config_instructions", lambda: ["org.md", "proj.md"]
    )
    merged = run_mod._merge_instructions(["cli-extra.md"])
    assert merged == ["org.md", "proj.md", "cli-extra.md"]


def test_resolve_config_instructions_reads_layered_config(tmp_path, monkeypatch):
    """A project praisonai.yaml `instructions:` list is surfaced (concat-merge).

    The runtime resolver concatenates list-valued keys across the hierarchy, so
    a project config extends rather than replaces any global list.
    """
    from praisonai_code.cli.commands import run as run_mod
    from praisonai_code.cli.configuration import resolver as resolver_mod

    (tmp_path / "praisonai.yaml").write_text(
        "instructions:\n  - docs/rules.md\n  - https://example.com/r.md\n"
    )
    monkeypatch.chdir(tmp_path)
    # Fresh resolver bound to this cwd (avoid cached singleton from other tests).
    resolver_mod._default_resolver = None

    out = run_mod._resolve_config_instructions()
    assert out == ["docs/rules.md", "https://example.com/r.md"]
