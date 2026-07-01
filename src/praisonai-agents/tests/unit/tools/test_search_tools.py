"""Tests for the capped ``grep`` and ``glob`` built-in search tools.

Covers:
1. Registration / lazy import via ``praisonaiagents.tools``.
2. ``grep`` content search (ripgrep path and pure-Python fallback).
3. ``glob`` file discovery.
4. Result capping + truncation hint.
5. Workspace containment (traversal rejection).
6. Case-insensitivity, no-match, and error handling.
"""

import os
from unittest.mock import patch

import pytest


@pytest.fixture()
def sample_tree(tmp_path, monkeypatch):
    """A small workspace with known content, made the cwd for containment."""
    (tmp_path / "a.py").write_text("def alpha():\n    return needle\n")
    (tmp_path / "b.py").write_text("def beta():\n    return NEEDLE\n")
    (tmp_path / "c.txt").write_text("nothing here\n")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "d.py").write_text("x = needle\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_grep_and_glob_are_registered():
    from praisonaiagents.tools import grep, glob
    assert callable(grep)
    assert callable(glob)


def test_grep_finds_matches_relative_paths(sample_tree):
    from praisonaiagents.tools import grep
    # Force the pure-Python fallback so this test is deterministic regardless of
    # whether ripgrep is installed on the machine/CI image running it.
    with patch("shutil.which", return_value=None):
        out = grep("needle", path=".")
    assert "a.py:2:" in out
    assert "src/d.py:1:" in out or os.path.join("src", "d.py") + ":1:" in out
    # match line content present
    assert "needle" in out
    # no absolute paths leaked on any output line
    assert not any(line.startswith("/") for line in out.splitlines())


def test_grep_python_fallback_when_no_ripgrep(sample_tree):
    from praisonaiagents.tools import grep
    with patch("shutil.which", return_value=None):
        out = grep("needle", path=".", glob="*.py")
    assert "a.py:" in out
    assert "c.txt" not in out  # glob restricts search to *.py files


def test_grep_glob_filters_by_pattern(sample_tree):
    from praisonaiagents.tools import grep
    with patch("shutil.which", return_value=None):
        out = grep("needle", path=".", glob="a.py")
    assert "a.py:" in out
    assert "src" not in out


def test_grep_case_insensitive(sample_tree):
    from praisonaiagents.tools import grep
    with patch("shutil.which", return_value=None):
        out = grep("NEEDLE", path=".", case_insensitive=True, glob="*.py")
    assert "a.py:" in out  # lowercase 'needle' found case-insensitively


def test_grep_no_match(sample_tree):
    from praisonaiagents.tools import grep
    with patch("shutil.which", return_value=None):
        out = grep("does_not_exist_zzz", path=".")
    assert out == "No matches found."


def test_grep_caps_results_with_hint(sample_tree):
    from praisonaiagents.tools import grep
    with patch("shutil.which", return_value=None):
        out = grep("def", path=".", glob="*.py", max_results=1)
    lines = out.splitlines()
    assert len(lines) == 2  # one match + hint
    assert "truncated at 1" in lines[-1]


def test_grep_rejects_traversal(sample_tree):
    from praisonaiagents.tools import grep
    out = grep("root", path="../../../../etc")
    assert "escapes the workspace" in out


def test_grep_empty_pattern(sample_tree):
    from praisonaiagents.tools import grep
    assert "non-empty" in grep("", path=".")


def test_glob_lists_files(sample_tree):
    from praisonaiagents.tools import glob
    out = glob("*.py", path=".")
    assert "a.py" in out
    assert "b.py" in out
    assert "c.txt" not in out


def test_glob_recursive(sample_tree):
    from praisonaiagents.tools import glob
    out = glob("**/*.py", path=".")
    assert "a.py" in out
    assert os.path.join("src", "d.py") in out or "src/d.py" in out


def test_glob_caps_results_with_hint(sample_tree):
    from praisonaiagents.tools import glob
    out = glob("**/*.py", path=".", max_results=1)
    lines = out.splitlines()
    assert len(lines) == 2
    assert "truncated at 1" in lines[-1]


def test_glob_no_match(sample_tree):
    from praisonaiagents.tools import glob
    assert glob("*.nonexistent", path=".") == "No files found."


def test_glob_rejects_traversal(sample_tree):
    from praisonaiagents.tools import glob
    out = glob("**/*", path="../../../../etc")
    assert "escapes the workspace" in out


def test_glob_honours_gitignore(sample_tree):
    from praisonaiagents.tools import glob
    (sample_tree / ".gitignore").write_text("b.py\n")
    out = glob("*.py", path=".")
    assert "a.py" in out
    assert "b.py" not in out


def test_grep_single_file_path_fallback(sample_tree):
    from praisonaiagents.tools import grep
    # A single file path must work on the pure-Python fallback (regression:
    # os.walk on a file yielded nothing -> silent "No matches found.").
    with patch("shutil.which", return_value=None):
        out = grep("needle", path="a.py")
    assert "a.py:2:" in out


def test_grep_uses_ripgrep_branch_when_available(sample_tree):
    from praisonaiagents.tools import grep
    from unittest.mock import MagicMock
    fake = MagicMock(returncode=0, stdout="a.py:2: return needle\n", stderr="")
    with patch("shutil.which", return_value="/usr/bin/rg"), \
            patch("subprocess.run", return_value=fake) as run:
        out = grep("needle", path=".")
    assert run.called
    # no per-file --max-count (diverges from fallback total cap)
    argv = run.call_args[0][0]
    assert not any(str(a).startswith("--max-count") for a in argv)
    assert "a.py:2:" in out


def test_glob_gitignore_directory_only_rule(sample_tree):
    from praisonaiagents.tools import glob
    gen = sample_tree / "generated"
    gen.mkdir()
    (gen / "e.py").write_text("x = 1\n")
    (sample_tree / ".gitignore").write_text("generated/\n")
    out = glob("**/*.py", path=".")
    assert "a.py" in out
    assert "generated" not in out  # dir-only rule excludes files beneath it


def test_glob_gitignore_negation_reinclude(sample_tree):
    from praisonaiagents.tools import glob
    (sample_tree / "keep.log").write_text("x\n")
    (sample_tree / "drop.log").write_text("y\n")
    (sample_tree / ".gitignore").write_text("*.log\n!keep.log\n")
    out = glob("*.log", path=".")
    assert "keep.log" in out  # re-included by the negation rule
    assert "drop.log" not in out
