"""Tests for AGENTS.md walk-up discovery and layered merge."""

from pathlib import Path

import pytest

from praisonai.integration.context_files import load_context_files


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
    root, nested = project
    (root / "AGENTS.md").write_text("ROOT")

    # cwd == root: walk-up dirs would include root once; ensure no double-read.
    out = load_context_files(cwd=root)
    assert out.count("ROOT") == 1


def test_no_files_returns_empty(project):
    root, nested = project
    out = load_context_files(cwd=nested)
    assert out == ""
