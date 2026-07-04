"""Tests for on-demand instruction-file attachment (monorepo subtree rules)."""

import os
from pathlib import Path

import pytest

from praisonaiagents.context import (
    InstructionFileAttacher,
    discover_instruction_files,
)


@pytest.fixture
def monorepo(tmp_path: Path) -> Path:
    """Build a monorepo fixture with root + subtree AGENTS.md files.

    tmp_path/
      .git/
      AGENTS.md                 (root conventions)
      packages/
        foo/
          AGENTS.md             (foo subtree conventions)
          src/module.py
        bar/
          baz.py                (no local instructions)
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / "AGENTS.md").write_text("ROOT conventions", encoding="utf-8")

    foo = tmp_path / "packages" / "foo"
    (foo / "src").mkdir(parents=True)
    (foo / "AGENTS.md").write_text("FOO subtree conventions", encoding="utf-8")
    (foo / "src" / "module.py").write_text("print('foo')\n", encoding="utf-8")

    bar = tmp_path / "packages" / "bar"
    bar.mkdir(parents=True)
    (bar / "baz.py").write_text("print('bar')\n", encoding="utf-8")

    return tmp_path


def test_subtree_file_attached_only_after_read(monorepo: Path):
    """The subtree AGENTS.md is attached only after a file under it is read."""
    attacher = InstructionFileAttacher(project_root=monorepo)

    text = attacher.attach_for_path(str(monorepo / "packages" / "foo" / "src" / "module.py"))

    assert "FOO subtree conventions" in text
    assert "ROOT conventions" in text
    # Root appears first (general), subtree last (nearest-wins).
    assert text.index("ROOT conventions") < text.index("FOO subtree conventions")


def test_second_touch_same_subtree_returns_nothing(monorepo: Path):
    """Touching another file in the same subtree does not re-attach."""
    attacher = InstructionFileAttacher(project_root=monorepo)

    first = attacher.attach_for_path(str(monorepo / "packages" / "foo" / "src" / "module.py"))
    assert "FOO subtree conventions" in first

    # A different file in the same directory (already visited) yields nothing.
    (monorepo / "packages" / "foo" / "src" / "other.py").write_text("x", encoding="utf-8")
    second = attacher.attach_for_path(str(monorepo / "packages" / "foo" / "src" / "other.py"))
    assert second == ""


def test_dedup_against_already_loaded(monorepo: Path):
    """Content present in the up-front layer is not re-attached."""
    attacher = InstructionFileAttacher(
        project_root=monorepo,
        already_loaded="ROOT conventions",
    )
    text = attacher.attach_for_path(str(monorepo / "packages" / "foo" / "src" / "module.py"))

    assert "FOO subtree conventions" in text
    assert "ROOT conventions" not in text


def test_dedup_does_not_drop_on_substring_overlap(monorepo: Path):
    """A distinct subtree file is not dropped just because its normalized text
    is a substring of the larger already-loaded blob."""
    (monorepo / "packages" / "foo" / "AGENTS.md").write_text(
        "conventions", encoding="utf-8"
    )
    attacher = InstructionFileAttacher(
        project_root=monorepo,
        already_loaded="ROOT conventions\n\nother stuff here",
    )
    text = attacher.attach_for_path(
        str(monorepo / "packages" / "foo" / "src" / "module.py")
    )
    # "conventions" is a substring of the preloaded blob but is a distinct file,
    # so it must still be attached.
    assert "conventions" in text
    # The exact preloaded block is still skipped.
    assert "ROOT conventions" not in text


def test_sibling_subtree_without_instructions(monorepo: Path):
    """A sibling subtree with no local file still surfaces root conventions once."""
    attacher = InstructionFileAttacher(project_root=monorepo)
    text = attacher.attach_for_path(str(monorepo / "packages" / "bar" / "baz.py"))
    assert "ROOT conventions" in text
    assert "FOO subtree conventions" not in text


def test_char_budget_bounds_output(monorepo: Path):
    """The character budget bounds total on-demand attachment."""
    (monorepo / "AGENTS.md").write_text("A" * 50, encoding="utf-8")
    (monorepo / "packages" / "foo" / "AGENTS.md").write_text("B" * 50, encoding="utf-8")

    attacher = InstructionFileAttacher(project_root=monorepo, max_chars=60)
    text = attacher.attach_for_path(str(monorepo / "packages" / "foo" / "src" / "module.py"))

    # Instruction content (excluding joiners/notice) stays within budget: the
    # 50-char root file plus at most 10 chars of the subtree file.
    content_chars = text.replace("\n\n", "").replace("... (truncated)", "")
    assert len(content_chars) <= 60
    assert "truncated" in text


def test_discover_instruction_files_helper(monorepo: Path):
    """Stateless helper lists governing files root -> nearest."""
    found = discover_instruction_files(
        str(monorepo / "packages" / "foo" / "src" / "module.py"),
        project_root=str(monorepo),
    )
    assert found[0].endswith(os.path.join("", "AGENTS.md"))
    assert found[0] == str(monorepo / "AGENTS.md")
    assert found[-1] == str(monorepo / "packages" / "foo" / "AGENTS.md")


def test_no_instruction_files_returns_empty(tmp_path: Path):
    """When no instruction files exist, attachment yields empty string."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "file.py").write_text("x", encoding="utf-8")
    attacher = InstructionFileAttacher(project_root=tmp_path)
    assert attacher.attach_for_path(str(tmp_path / "file.py")) == ""


def test_file_outside_project_root_does_not_escape(monorepo: Path, tmp_path_factory):
    """A file outside project_root must never surface external AGENTS.md files."""
    outside = tmp_path_factory.mktemp("outside")
    (outside / "AGENTS.md").write_text("OUTSIDE conventions", encoding="utf-8")
    (outside / "rogue.py").write_text("print('x')\n", encoding="utf-8")

    attacher = InstructionFileAttacher(project_root=monorepo)
    text = attacher.attach_for_path(str(outside / "rogue.py"))

    assert "OUTSIDE conventions" not in text
    assert text == ""
