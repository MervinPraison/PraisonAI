"""T-06: the user's git settings never reach the internal shadow repo.

- core.fsmonitor=true started git's fsmonitor daemon (built in on macOS and
  Windows). It held the command's stdout pipe open, so every checkpoint
  initialize waited 30 s and failed.
- A global commit.gpgsign=true made the shadow commit try to sign; a global
  core.hooksPath ran the user's hooks on internal commits.
"""
import asyncio
import shutil

import pytest

from praisonaiagents.checkpoints.service import CheckpointService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def hostile_global_git(tmp_path, monkeypatch):
    hooks = tmp_path / "user-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    cfg = tmp_path / "gitconfig"
    cfg.write_text(
        "[commit]\n\tgpgsign = true\n"
        "[gpg]\n\tprogram = /nonexistent/gpg\n"
        f"[core]\n\thooksPath = {hooks}\n\tfsmonitor = true\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    return cfg


def _service(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("x")
    return CheckpointService(workspace_dir=str(ws), storage_dir=str(tmp_path / "store"))


def test_initialize_ignores_user_git_settings(tmp_path, hostile_global_git):
    service = _service(tmp_path)
    assert asyncio.run(asyncio.wait_for(service.initialize(), timeout=20)) is True


def test_old_shadow_repo_with_fsmonitor_is_overridden(tmp_path):
    service = _service(tmp_path)
    assert asyncio.run(service.initialize()) is True
    # A shadow repo made by an earlier version has core.fsmonitor=true in its config.
    asyncio.run(service._run_git("config", "core.fsmonitor", "true"))
    effective = asyncio.run(service._run_git("config", "--get", "core.fsmonitor"))
    assert effective == "false"
