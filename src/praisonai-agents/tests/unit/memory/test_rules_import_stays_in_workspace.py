"""Rules ``@import`` and FileMemory checkpoints stay inside their roots.

Project rule files (workspace or git root) may import from the project, the
global rules folder and, through the documented ``@~/...`` form, Markdown files
in the home directory. User-level rule files may also import from their own
folder and any home file. FileMemory checkpoints only
snapshot and restore files inside the working directory.
"""

import json
import logging

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def layout(tmp_path, monkeypatch):
    home = tmp_path / "home"
    rules_dir = home / ".praisonai" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "shared.md").write_text("SHARED-RULE")
    (home / "elsewhere.txt").write_text("HOME-OUTSIDE")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.txt").write_text("OUTSIDE-TEXT")
    ws = tmp_path / "repo" / "ws"
    (ws / "docs").mkdir(parents=True)
    (ws / ".git").mkdir()
    (ws / "docs" / "style.md").write_text("STYLE-RULE")
    (ws / "local.md").write_text("LOCAL-RULE")
    (ws / "link").symlink_to(outside)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai_home"))
    monkeypatch.chdir(ws)
    return ws, rules_dir, outside


def _expand(ws, rules_dir, text, base=None):
    rm = RulesManager(workspace_path=str(ws), global_rules_path=str(rules_dir))
    return rm._process_imports(text, base or ws)


def test_imports_inside_the_workspace_and_rules_folder_still_work(layout):
    ws, rules_dir, _ = layout
    out = _expand(ws, rules_dir, "@docs/style.md\n@./local.md\n@~/.praisonai/rules/shared.md")
    assert "STYLE-RULE" in out and "LOCAL-RULE" in out and "SHARED-RULE" in out


@pytest.mark.parametrize("ref", ["absolute", "dotdot", "dot_slash_escape", "symlink", "home"])
def test_project_imports_outside_are_refused_with_a_warning(layout, caplog, ref):
    ws, rules_dir, outside = layout
    text = {"absolute": f"@{outside / 'note.txt'}", "dotdot": "@../../outside/note.txt",
            "dot_slash_escape": "@./../../outside/note.txt", "symlink": "@link/note.txt",
            "home": "@~/elsewhere.txt"}[ref]
    with caplog.at_level(logging.WARNING):
        out = _expand(ws, rules_dir, text)
    assert "OUTSIDE-TEXT" not in out and "HOME-OUTSIDE" not in out
    assert any("refused" in r.getMessage() for r in caplog.records)


def test_mentions_are_left_alone(layout):
    ws, rules_dir, _ = layout
    assert _expand(ws, rules_dir, "ask @alice about it") == "ask @alice about it"


def test_user_level_rule_files_keep_home_imports(layout):
    ws, rules_dir, outside = layout
    assert "HOME-OUTSIDE" in _expand(ws, rules_dir, "@~/elsewhere.txt", base=rules_dir)
    (rules_dir.parent.parent / "notes.md").write_text("HOME-MD")
    assert "HOME-MD" in _expand(ws, rules_dir, "@~/notes.md")
    assert "OUTSIDE-TEXT" not in _expand(ws, rules_dir, f"@{outside / 'note.txt'}", base=rules_dir)


def _memory(tmp_path):
    from praisonaiagents.memory.file_memory import FileMemory
    return FileMemory(user_id="alice", config={"base_path": str(tmp_path / "mem")})


@pytest.mark.parametrize("path", ["absolute", "dotdot", "symlink"])
def test_checkpoint_does_not_snapshot_files_outside_cwd(layout, tmp_path, path):
    ws, _, outside = layout
    ref = {"absolute": str(outside / "note.txt"), "dotdot": "../../outside/note.txt",
           "symlink": "link/note.txt"}[path]
    mem = _memory(tmp_path)
    cid = mem.create_checkpoint("c1", include_files=[ref, "local.md"])
    data = json.loads((mem.user_path / "checkpoints" / f"{cid}.json").read_text())
    assert "OUTSIDE-TEXT" not in json.dumps(data)
    assert data["file_snapshots"] == {"local.md": "LOCAL-RULE"}


def test_restore_does_not_write_files_outside_cwd(layout, tmp_path):
    ws, _, outside = layout
    mem = _memory(tmp_path)
    cid = mem.create_checkpoint("c2")
    ckpt = mem.user_path / "checkpoints" / f"{cid}.json"
    data = json.loads(ckpt.read_text())
    data["file_snapshots"] = {str(outside / "planted.txt"): "x", "restored.md": "ok"}
    ckpt.write_text(json.dumps(data))
    assert mem.restore_checkpoint(cid, restore_files=True)
    assert not (outside / "planted.txt").exists()
    assert (ws / "restored.md").read_text() == "ok"
