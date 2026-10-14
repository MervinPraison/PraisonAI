"""Edited nested instruction files are re-attached by the praisonai_bot attacher.

``praisonai_code.cli.commands.run`` and the interactive core prefer this copy
(directly or via the ``praisonai.integration.context_files`` shim) when
``praisonai_bot`` is installed, so it must pick up edits like the resident copy.
"""

import os
from pathlib import Path

from praisonai_bot.integration.context_files import PathContextAttacher


def _bump_mtime(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))


def test_subtree_attacher_reattaches_edited_nested_instructions(tmp_path):
    pkg = tmp_path / "packages" / "foo"
    pkg.mkdir(parents=True)
    rules = pkg / "AGENTS.md"
    rules.write_text("Old package rule.\n")
    target = pkg / "mod.py"
    target.write_text("")

    attacher = PathContextAttacher(max_chars=0)
    assert "Old package rule." in attacher.attach_for_path(target)
    # Unchanged: cached result is reused.
    assert "Old package rule." in attacher.attach_for_path(target)

    rules.write_text("New package rule.\n")
    _bump_mtime(rules)
    assert "New package rule." in attacher.attach_for_path(target)


def test_subtree_attacher_picks_up_newly_added_nested_instructions(tmp_path):
    pkg = tmp_path / "packages" / "foo"
    pkg.mkdir(parents=True)
    target = pkg / "mod.py"
    target.write_text("")

    attacher = PathContextAttacher(max_chars=0)
    assert "Added rule." not in attacher.attach_for_path(target)

    (pkg / "AGENTS.md").write_text("Added rule.\n")
    assert "Added rule." in attacher.attach_for_path(target)
