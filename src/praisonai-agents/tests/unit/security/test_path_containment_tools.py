"""Skill tools, ``search_files`` and the permission allowlist stay inside their root."""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="symlink fixtures need POSIX")

SECRET = "CANARY-5d1e77"
ESCAPES = ("absolute", "dotdot", "sibling", "tilde", "symlink")


@pytest.fixture
def box(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "skill" / "scripts").mkdir(parents=True)
    (ws / "skill" / "SKILL.md").write_text("ok\n")
    (ws / "skill" / "scripts" / "ok.py").write_text("print('ok')\n")
    outside, sibling, home = tmp_path / "outside", tmp_path / "ws-sib", tmp_path / "home"
    for d in (outside, sibling, home):
        (d / "scripts").mkdir(parents=True)
        (d / "canary.txt").write_text(SECRET + "\n")
        (d / "scripts" / "run.py").write_text(f"print('{SECRET}')\n")
    os.symlink(outside, ws / "link")
    os.symlink(outside / "canary.txt", ws / "skill" / "leak.txt")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai_home"))
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    monkeypatch.chdir(ws)
    dirs = {
        "absolute": str(outside),
        "dotdot": "../outside",
        "sibling": str(sibling),
        "tilde": "~",
        "symlink": "link",
    }
    return ws, dirs


def _skills(ws):
    from praisonaiagents.tools.skill_tools import SkillTools

    return SkillTools(working_directory=str(ws))


@pytest.mark.parametrize("vector", ESCAPES)
def test_skill_tools_refuse_escape(box, vector):
    ws, dirs = box
    tools = _skills(ws)
    for result in (
        tools.read_skill_file(dirs[vector], "canary.txt"),
        tools.list_skill_scripts(dirs[vector]),
        tools.run_skill_script(f"{dirs[vector]}/scripts/run.py"),
    ):
        assert SECRET not in result and '"name": "run.py"' not in result, result


def test_skill_file_symlink_inside_skill_is_refused(box):
    ws, _ = box
    assert SECRET not in _skills(ws).read_skill_file("skill", "leak.txt")


def test_skill_tools_still_work_inside(box):
    ws, _ = box
    tools = _skills(ws)
    assert tools.read_skill_file("skill", "SKILL.md") == "ok\n"
    assert "ok.py" in tools.list_skill_scripts("skill")
    assert "ok" in tools.run_skill_script("skill/scripts/ok.py")


@pytest.mark.parametrize("vector", ESCAPES)
def test_search_files_refuses_escape(box, vector):
    from praisonaiagents.tools.edit_tools import EditTools

    ws, dirs = box
    tools = EditTools(root=str(ws))
    assert SECRET not in tools.search_files(dirs[vector], "CANARY-5d1e")
    assert SECRET not in tools.search_files(".", "CANARY-5d1e", f"{dirs[vector]}/canary.txt")


def test_search_files_walk_skips_symlink_out(box):
    from praisonaiagents.tools.edit_tools import EditTools

    ws, _ = box
    tools = EditTools(root=str(ws))
    assert SECRET not in tools.search_files(".", "CANARY-5d1e")
    assert "SKILL.md" in tools.search_files(".", "ok")


@pytest.mark.parametrize("vector", ESCAPES)
def test_allowlist_paths_are_contained(box, vector):
    from praisonaiagents.approval import PermissionAllowlist

    ws, dirs = box
    allow = PermissionAllowlist()
    allow.add_tool("write_file", paths=[str(ws)])
    assert allow.is_allowed("write_file", str(ws / "skill" / "SKILL.md"))
    assert allow.is_allowed("write_file", "skill/SKILL.md")
    assert not allow.is_allowed("write_file", f"{dirs[vector]}/canary.txt")
