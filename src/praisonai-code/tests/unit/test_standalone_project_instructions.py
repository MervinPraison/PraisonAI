"""Standalone regression tests for project instructions & rules (issue #4337).

On a lean ``pip install praisonai-code`` (no ``praisonai`` wrapper, no
``praisonai_bot`` support package) the terminal product must still:

* attach subtree ``AGENTS.md`` on cross-directory file reads,
* resolve ``--instructions`` globs/URLs up front, and
* run ``praisonai rules list/add/clear`` natively.

These tests simulate the absence of the optional packages by blocking their
import so the resident ``praisonai_code`` implementation is exercised.
"""

from types import SimpleNamespace

import pytest

# Import the command modules up front (with the optional packages available) so
# the ``no_optional_packages`` fixture only affects the *runtime* helper lookup
# inside ``_wire_subtree_context_hook`` / the rules handler, not their import.
from praisonai_code.cli.commands.run import _wire_subtree_context_hook
from praisonai_code.cli.commands import rules as rules_cmd
from praisonai_code.integration import context_files as _resident_ctx  # noqa: F401


@pytest.fixture
def no_optional_packages(monkeypatch):
    """Make ``praisonai_bot`` and the ``praisonai`` wrapper un-importable.

    Simulates a standalone ``praisonai-code`` install so the resident helper
    (``praisonai_code.integration.context_files``) is the only one available at
    runtime. ``praisonai_code`` itself is a distinct top-level package and is
    unaffected.
    """
    import importlib
    import sys

    for name in list(sys.modules):
        if name == "praisonai_bot" or name.startswith("praisonai_bot."):
            monkeypatch.delitem(sys.modules, name, raising=False)
        if name == "praisonai" or name.startswith("praisonai."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    real_import_module = importlib.import_module

    def _blocked_import_module(name, *args, **kwargs):
        if name == "praisonai_bot" or name.startswith("praisonai_bot."):
            raise ImportError(f"blocked in standalone test: {name}")
        if name == "praisonai" or name.startswith("praisonai."):
            raise ImportError(f"blocked in standalone test: {name}")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", _blocked_import_module)


@pytest.fixture
def monorepo(tmp_path, monkeypatch):
    """A monorepo with a root and a nested package, with a fake git root."""
    root = tmp_path / "repo"
    foo = root / "packages" / "foo"
    foo.mkdir(parents=True)
    (root / "AGENTS.md").write_text("ROOT RULES")
    (foo / "AGENTS.md").write_text("FOO RULES")
    # Force deterministic git-root detection on the *resident* helper.
    monkeypatch.setattr(
        "praisonai_code.integration.context_files._get_git_root",
        lambda start: root,
    )
    return root, foo


def _fire_after_tool(registry, tool_input):
    from praisonaiagents.hooks import HookEvent

    event = SimpleNamespace(tool_input=tool_input)
    contexts = []
    for hook in registry.get_hooks(HookEvent.AFTER_TOOL):
        func = getattr(hook, "func", hook)
        result = func(event)
        if result is not None and getattr(result, "additional_context", None):
            contexts.append(result.additional_context)
    return "\n".join(contexts)


def test_subtree_hook_wired_without_optional_packages(
    monorepo, no_optional_packages
):
    """Subtree AGENTS.md attaches on cross-dir reads with no wrapper/bot."""
    _root, foo = monorepo
    agent_config = {"name": "RunAgent"}

    _wire_subtree_context_hook(agent_config)

    registry = agent_config.get("hooks")
    assert registry is not None, "resident subtree hook must register standalone"

    context = _fire_after_tool(registry, {"file_path": str(foo / "bar.py")})
    assert "FOO RULES" in context


def test_instruction_sources_resolved_without_optional_packages(
    tmp_path, monkeypatch, no_optional_packages
):
    """``--instructions`` globs resolve natively on a standalone install."""
    monkeypatch.setattr(
        "praisonai_code.integration.context_files._get_git_root",
        lambda start: tmp_path,
    )
    (tmp_path / "a.md").write_text("ORG STANDARD A")
    (tmp_path / "b.md").write_text("ORG STANDARD B")

    agent_config = {"name": "RunAgent"}
    _wire_subtree_context_hook(
        agent_config, instructions=[str(tmp_path / "*.md")]
    )

    backstory = agent_config.get("backstory") or ""
    assert "ORG STANDARD A" in backstory
    assert "ORG STANDARD B" in backstory
    assert "# Project Instructions" in backstory


def test_resident_context_files_is_dependency_free(no_optional_packages):
    """The resident helper imports and exposes the expected API standalone."""
    from praisonai_code.integration import context_files

    assert callable(context_files.resolve_instruction_sources)
    assert callable(context_files.build_subtree_context_hook)
    assert callable(context_files.file_tool_matcher)


# --- Native rules command --------------------------------------------------


def test_rules_list_native_without_wrapper(tmp_path, monkeypatch, capsys):
    """``rules list`` uses core RulesManager and never touches the wrapper."""
    (tmp_path / "AGENTS.md").write_text("be concise")
    monkeypatch.chdir(tmp_path)

    def _boom(*_a, **_k):
        raise AssertionError("wrapper fallback must not be used standalone")

    monkeypatch.setattr(rules_cmd, "_fallback", _boom)

    rules_cmd.rules_list()
    out = capsys.readouterr().out
    # AGENTS.md is discovered as a root instruction rule.
    assert "AGENTS" in out or "agents" in out.lower()


def test_rules_add_then_list_native(tmp_path, monkeypatch, capsys):
    """``rules add`` creates a workspace rule surfaced by ``rules list``."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        rules_cmd,
        "_fallback",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no fallback")),
    )

    rules_cmd.rules_add("style", "use tabs")
    add_out = capsys.readouterr().out
    assert "style" in add_out

    rules_cmd.rules_list()
    list_out = capsys.readouterr().out
    assert "style" in list_out


def test_rules_clear_native(tmp_path, monkeypatch, capsys):
    """``rules clear`` removes CLI-created rules."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        rules_cmd,
        "_fallback",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no fallback")),
    )

    rules_cmd.rules_add("style", "use tabs")
    capsys.readouterr()

    rules_cmd.rules_clear()
    clear_out = capsys.readouterr().out
    assert "Cleared" in clear_out
