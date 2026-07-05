"""Tests for AGENTS.md walk-up discovery and layered merge."""

from pathlib import Path

import pytest

from praisonai.integration.context_files import (
    PathContextAttacher,
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
