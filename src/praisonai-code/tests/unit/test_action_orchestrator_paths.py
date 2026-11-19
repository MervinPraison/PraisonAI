"""Action Orchestrator file steps stay inside the workspace."""

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

from praisonai_code.cli.features import action_orchestrator as ao

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="symlink fixture needs POSIX")

ESCAPES = ["../workspace-sib/pwned.txt", "../outside/pwned.txt", "link/pwned.txt"]


@pytest.fixture
def setup(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "keep.txt").write_text("keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("victim")
    os.symlink(outside, ws / "link")
    orch = ao.ActionOrchestrator(SimpleNamespace(config=SimpleNamespace(workspace=str(ws))))
    return orch, tmp_path


def _run(orch, action, target="", **params):
    step = ao.ActionStep(id="s", action_type=action, description="d", target=target, params=params)
    return asyncio.run(orch._apply_step(step))


@pytest.mark.parametrize("target", ESCAPES)
def test_create_and_rename_refuse_escape(setup, target):
    orch, tmp = setup
    with pytest.raises(ValueError):
        _run(orch, ao.ActionType.FILE_CREATE, target, content="x")
    with pytest.raises(ValueError):
        _run(orch, ao.ActionType.FILE_RENAME, source="keep.txt", dest=target)
    assert not list(tmp.glob("*/pwned.txt"))
    assert (tmp / "workspace" / "keep.txt").exists()


@pytest.mark.parametrize("target", ["../outside/victim.txt", "link/victim.txt"])
def test_edit_and_delete_refuse_escape(setup, target):
    orch, tmp = setup
    with pytest.raises(ValueError):
        _run(orch, ao.ActionType.FILE_EDIT, target, new_content="pwned")
    with pytest.raises(ValueError):
        _run(orch, ao.ActionType.FILE_DELETE, target)
    assert (tmp / "outside" / "victim.txt").read_text() == "victim"


def test_inside_paths_still_work(setup):
    orch, tmp = setup
    _run(orch, ao.ActionType.FILE_CREATE, "sub/new.txt", content="hi")
    assert (tmp / "workspace" / "sub" / "new.txt").read_text() == "hi"
