"""MCP tools that take a server file path keep it inside the working directory.

``test_every_path_tool_is_covered`` scans the MCP tool registry, so a new
tool with a path parameter fails here until it is probed or exempted.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
import types

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="symlink fixture needs POSIX")

ESCAPES = ("absolute", "dotdot", "sibling", "tilde", "symlink")

# tool name -> keyword that carries the path
PROBED = {
    "praisonai.files.create": "file_path",
    "praisonai.ocr": "image_path",
    "praisonai.audio.transcribe": "file_path",
    "praisonai.workflow.run_file": "file_path",
    "praisonai.knowledge.add": "source",
    "praisonai.workflow.validate": "file_path",
    "praisonai.workflow.show": "file_path",
    "praisonai.deploy.validate": "config_path",
}
EXEMPT = {
    "praisonai.fine_tuning.create": "training_file is a provider file id",
    "praisonai.containers.create": "image is a container image name",
    "praisonai.containers.file_read": "path inside the remote container",
    "praisonai.containers.file_write": "path inside the remote container",
    "praisonai.deploy.status": "config_path goes through _resolve_cwd_yaml_path",
    "praisonai.skills.load": "skill_path is a name matched against discovered skills (test below)",
    "praisonai.schedule.add": "workflow_path becomes the job's message text; no file is opened (test below)",
}
PENDING: dict = {}  # may only shrink; empty now
_PATH_PARAM = re.compile(
    r"(^|_)(path|paths|file|filepath|filename|dir|directory|folder|src|dst|root|source|document|image)$"
)


@pytest.fixture(scope="module")
def registry():
    from praisonai_mcp.mcp_server.adapters import register_all
    from praisonai_mcp.mcp_server.registry import _tool_registry

    if _tool_registry.get("praisonai.files.create") is None:
        register_all()
    return _tool_registry


@pytest.fixture
def box(tmp_path, monkeypatch):
    ws, outside, sibling, home = (tmp_path / n for n in ("ws", "outside", "ws-sib", "home"))
    for d in (ws, outside, sibling, home):
        d.mkdir()
    for d in (outside, sibling, home):
        (d / "secret.yaml").write_text("secret: CANARY-31c9\n")
    os.symlink(outside, ws / "link")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(ws)
    seen = []

    def record(*args, **kwargs):
        seen.extend(str(v) for v in (*args, *kwargs.values()))
        return "ok"

    import praisonai_mcp._wrapper_bridge as bridge
    monkeypatch.setattr(bridge, "wrapper_callable", lambda *a, **k: _Recorder(record))
    fake_knowledge = types.ModuleType("praisonaiagents.knowledge")
    fake_knowledge.Knowledge = lambda *a, **k: types.SimpleNamespace(add=record)
    monkeypatch.setitem(sys.modules, "praisonaiagents.knowledge", fake_knowledge)
    paths = {
        "absolute": str(outside / "secret.yaml"),
        "dotdot": "../outside/secret.yaml",
        "sibling": str(sibling / "secret.yaml"),
        "tilde": "~/secret.yaml",
        "symlink": "link/secret.yaml",
    }
    return {"paths": paths, "seen": seen}


class _Recorder:
    """Stands in for any wrapper capability or class; records what it is given."""

    def __init__(self, record):
        self._record = record

    def __call__(self, *args, **kwargs):
        self._record(*args, **kwargs)
        return self

    def __getattr__(self, name):
        return self


def test_every_path_tool_is_covered(registry):
    found = {
        t.name
        for t in registry._tools.values()
        if any(_PATH_PARAM.search(p) for p in inspect.signature(t.handler).parameters)
    }
    assert {"praisonai.files.create", "praisonai.workflow.run_file"} <= found  # scan control
    unknown = found - set(PROBED) - set(EXEMPT) - set(PENDING)
    assert not unknown, f"MCP tool(s) take a path but are not probed: {sorted(unknown)}"


@pytest.mark.parametrize("vector", ESCAPES)
@pytest.mark.parametrize("tool", sorted(PROBED))
def test_tool_does_not_open_outside(registry, box, tool, vector):
    handler = registry.get(tool).handler
    try:
        result = handler(**{PROBED[tool]: box["paths"][vector]})
    except ValueError:
        result = "refused"
    assert "CANARY-31c9" not in str(result)
    assert not any("secret.yaml" in v for v in box["seen"]), f"outside path passed on: {box['seen']}"


def test_skills_load_does_not_open_a_path(tmp_path, monkeypatch):
    """The name lookup cannot be pointed at a skill folder by path."""
    from praisonaiagents.skills import load_skill

    skill = tmp_path / "outside" / "rogue"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: rogue\ndescription: x\n---\nCANARY-31c9\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai_home"))
    monkeypatch.chdir(tmp_path)
    assert load_skill("rogue", [str(skill.parent)]) is not None  # control: the skill is valid
    for ref in (str(skill), str(skill / "SKILL.md"), "outside/rogue", "../outside/rogue"):
        assert load_skill(ref) is None


def test_schedule_add_does_not_read_workflow_path(registry, box, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai_home"))
    handler = registry.get("praisonai.schedule.add").handler
    for ref in box["paths"].values():
        assert "CANARY-31c9" not in str(handler(task_name="t", cron="hourly", workflow_path=ref))
    stored = "".join(p.read_text() for p in (tmp_path / "praisonai_home").rglob("*.json"))
    stored += "".join(p.read_text() for p in (tmp_path / "home").rglob("*.json"))
    assert "CANARY-31c9" not in stored
