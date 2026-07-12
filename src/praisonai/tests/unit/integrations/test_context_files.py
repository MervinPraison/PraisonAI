"""Tests for AGENTS.md walk-up discovery and layered merge."""

from pathlib import Path

import pytest

from types import SimpleNamespace

from praisonai.integration.context_files import (
    PathContextAttacher,
    build_subtree_context_hook,
    file_tool_matcher,
    load_context_files,
    load_context_files_for_path,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A nested project tree with a fake git root, no real git involved."""
    root = tmp_path / "repo"
    nested = root / "pkg" / "sub"
    nested.mkdir(parents=True)

    # Force git-root detection to the repo root, deterministically.
    monkeypatch.setattr(
        "praisonai.integration.context_files._get_git_root",
        lambda start: root,
    )
    return root, nested


def test_explicit_paths_are_cwd_only_and_override(project):
    root, nested = project
    (nested / "AGENTS.md").write_text("LOCAL")
    (root / "AGENTS.md").write_text("ROOT")

    out = load_context_files(["AGENTS.md"], cwd=nested)
    assert out == "LOCAL"


def test_subdirectory_finds_project_root_file(project):
    root, nested = project
    (root / "AGENTS.md").write_text("ROOT GUIDANCE")

    out = load_context_files(cwd=nested)
    assert "ROOT GUIDANCE" in out


def test_monorepo_layering_order_root_then_nearer(project):
    root, nested = project
    (root / "AGENTS.md").write_text("ROOT")
    (nested / "AGENTS.md").write_text("PACKAGE")

    out = load_context_files(cwd=nested)
    # Root appears first, nearer (package) file appears last (higher precedence).
    assert out.index("ROOT") < out.index("PACKAGE")


def test_walk_up_disabled_only_reads_cwd(project):
    root, nested = project
    (root / "AGENTS.md").write_text("ROOT")
    (nested / "AGENTS.md").write_text("PACKAGE")

    out = load_context_files(cwd=nested, walk_up=False)
    assert out == "PACKAGE"


def test_global_file_is_lowest_precedence(project, monkeypatch, tmp_path):
    root, nested = project
    home = tmp_path / "home"
    (home / ".praisonai").mkdir(parents=True)
    (home / ".praisonai" / "AGENTS.md").write_text("GLOBAL")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    (root / "AGENTS.md").write_text("ROOT")

    out = load_context_files(cwd=nested)
    assert out.index("GLOBAL") < out.index("ROOT")


def test_duplicate_paths_deduplicated(project):
    root, _nested = project
    (root / "AGENTS.md").write_text("ROOT")

    # cwd == root: walk-up dirs would include root once; ensure no double-read.
    out = load_context_files(cwd=root)
    assert out.count("ROOT") == 1


def test_no_files_returns_empty(project):
    _root, nested = project
    out = load_context_files(cwd=nested)
    assert out == ""


def test_walk_up_disabled_skips_global_file(project, monkeypatch, tmp_path):
    root, nested = project
    home = tmp_path / "home"
    (home / ".praisonai").mkdir(parents=True)
    (home / ".praisonai" / "AGENTS.md").write_text("GLOBAL")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    (nested / "AGENTS.md").write_text("PACKAGE")

    out = load_context_files(cwd=nested, walk_up=False)
    # walk_up=False is cwd-only: the global file must not leak in.
    assert out == "PACKAGE"


@pytest.fixture
def monorepo(tmp_path, monkeypatch):
    """A monorepo with a root and two sibling packages, fake git root."""
    root = tmp_path / "repo"
    foo = root / "packages" / "foo"
    bar = root / "packages" / "bar"
    foo.mkdir(parents=True)
    bar.mkdir(parents=True)
    monkeypatch.setattr(
        "praisonai.integration.context_files._get_git_root",
        lambda start: root,
    )
    return root, foo, bar


def test_subtree_attached_only_after_file_under_it_is_read(monorepo):
    root, foo, _bar = monorepo
    (root / "AGENTS.md").write_text("ROOT RULES")
    (foo / "AGENTS.md").write_text("FOO RULES")

    attacher = PathContextAttacher(already_loaded="ROOT RULES")

    # Touch a file under packages/foo -> the subtree file is attached now.
    out = attacher.attach_for_path(foo / "main.py")
    assert "FOO RULES" in out
    # Root rules were already loaded up front, so they are not re-attached.
    assert "ROOT RULES" not in out


def test_sibling_without_instructions_attaches_nothing_new(monorepo):
    root, _foo, bar = monorepo
    (root / "AGENTS.md").write_text("ROOT RULES")

    attacher = PathContextAttacher(already_loaded="ROOT RULES")
    out = attacher.attach_for_path(bar / "main.py")
    # bar has no own AGENTS.md and root was already loaded -> nothing new.
    assert out == ""


def test_dedup_against_already_loaded_up_front(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("FOO RULES")

    # Simulate the foo rules already being part of up-front context.
    attacher = PathContextAttacher(already_loaded="FOO RULES")
    out = attacher.attach_for_path(foo / "main.py")
    assert out == ""


def test_dedup_against_concatenated_already_loaded(monorepo):
    _root, foo, _bar = monorepo
    (_root / "AGENTS.md").write_text("ROOT RULES")
    (foo / "AGENTS.md").write_text("FOO RULES")

    # Up-front context is the concatenation produced by load_context_files().
    combined = "ROOT RULES\n\nFOO RULES"
    attacher = PathContextAttacher(already_loaded=combined)
    out = attacher.attach_for_path(foo / "main.py")
    # Both files were part of the concatenated up-front load -> nothing new.
    assert out == ""


def test_per_subtree_cache_avoids_rewalk(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("FOO RULES")

    attacher = PathContextAttacher()
    first = attacher.attach_for_path(foo / "a.py")
    assert "FOO RULES" in first
    # Second touch of the same directory returns cached result; and because the
    # file was already emitted, a different dir touch won't re-emit it.
    second = attacher.attach_for_path(foo / "b.py")
    assert second == first


def test_already_emitted_file_not_reattached_across_dirs(monorepo):
    _root, foo, _bar = monorepo
    sub = foo / "sub"
    sub.mkdir()
    (foo / "AGENTS.md").write_text("FOO RULES")

    attacher = PathContextAttacher()
    first = attacher.attach_for_path(foo / "a.py")
    assert "FOO RULES" in first
    # Touching a deeper dir walks up through foo again, but FOO RULES was
    # already emitted, so it is not duplicated.
    deeper = attacher.attach_for_path(sub / "b.py")
    assert "FOO RULES" not in deeper


def test_char_budget_bounds_output(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("X" * 500)

    attacher = PathContextAttacher(max_chars=100)
    out = attacher.attach_for_path(foo / "main.py")
    assert len(out) <= 100 + len("\n... [subtree context truncated]")
    assert "truncated" in out


def test_stateless_helper_discovers_nearest(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("FOO RULES")

    out = load_context_files_for_path(foo / "main.py")
    assert "FOO RULES" in out


def test_no_instruction_files_returns_empty(monorepo):
    _root, foo, _bar = monorepo
    attacher = PathContextAttacher()
    assert attacher.attach_for_path(foo / "main.py") == ""


# --- AFTER_TOOL hook wiring -------------------------------------------------


def _tool_event(tool_input):
    """Minimal AfterToolInput stand-in exposing ``tool_input``."""
    return SimpleNamespace(tool_input=tool_input)


def test_hook_injects_subtree_rules_on_file_touch(monorepo):
    root, foo, _bar = monorepo
    (root / "AGENTS.md").write_text("ROOT RULES")
    (foo / "AGENTS.md").write_text("FOO RULES")

    hook = build_subtree_context_hook(already_loaded="ROOT RULES")
    result = hook(_tool_event({"filepath": str(foo / "main.py")}))

    assert result is not None
    assert "FOO RULES" in result.additional_context
    # Root was already loaded up front -> not re-attached.
    assert "ROOT RULES" not in result.additional_context


def test_hook_dedups_across_subtree_dirs(monorepo):
    _root, foo, _bar = monorepo
    sub = foo / "sub"
    sub.mkdir()
    (foo / "AGENTS.md").write_text("FOO RULES")

    hook = build_subtree_context_hook()
    first = hook(_tool_event({"path": str(foo / "a.py")}))
    assert first is not None and "FOO RULES" in first.additional_context
    # Touching a deeper dir walks up through foo again, but FOO RULES was
    # already emitted, so it is not re-attached.
    second = hook(_tool_event({"path": str(sub / "b.py")}))
    assert second is None


def test_hook_accepts_alternate_path_keys(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("FOO RULES")

    hook = build_subtree_context_hook()
    result = hook(_tool_event({"file_path": str(foo / "main.py")}))
    assert result is not None
    assert "FOO RULES" in result.additional_context


def test_hook_noop_without_path(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("FOO RULES")

    hook = build_subtree_context_hook()
    assert hook(_tool_event({"command": "ls"})) is None
    assert hook(_tool_event(None)) is None


def test_hook_noop_when_no_instruction_files(monorepo):
    _root, foo, _bar = monorepo
    hook = build_subtree_context_hook()
    assert hook(_tool_event({"filepath": str(foo / "main.py")})) is None


def test_hook_respects_char_budget(monorepo):
    _root, foo, _bar = monorepo
    (foo / "AGENTS.md").write_text("X" * 500)

    hook = build_subtree_context_hook(max_chars=100)
    result = hook(_tool_event({"filepath": str(foo / "main.py")}))
    assert result is not None
    assert "truncated" in result.additional_context


def test_file_tool_matcher_matches_expected_tools():
    import re

    pattern = file_tool_matcher()
    for name in (
        "read_file",
        "edit_file",
        "write_file",
        "list_files",
        "acp_create_file",
        "acp_edit_file",
        "acp_delete_file",
    ):
        assert re.match(pattern, name), name
    assert not re.match(pattern, "bash")
    assert not re.match(pattern, "internet_search")


def test_hook_extracts_alternate_path_keys(project):
    root, nested = project
    (nested / "AGENTS.md").write_text("SUBTREE RULES")

    for key in ("file_path", "path", "filename", "target_file"):
        hook = build_subtree_context_hook()
        result = hook(_tool_event({key: str(nested / "main.py")}))
        assert result is not None, key
        assert "SUBTREE RULES" in result.additional_context, key
