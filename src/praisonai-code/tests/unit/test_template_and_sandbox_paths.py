"""Path checks in ``TemplateInterpolator`` (@file) and the sandbox executor.

``@file`` with no ``working_dir`` (bot adapters) stays inside the cwd. The
sandbox executor checks the argv it runs (``shlex``), with relative and
quoted paths resolved against the run directory.
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")


@pytest.fixture
def box(tmp_path, monkeypatch):
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("CANARY-5e1d")
    (ws / "inside.txt").write_text("INSIDE-OK")
    os.symlink(outside, ws / "link")
    monkeypatch.chdir(ws)
    return ws, outside


@pytest.mark.parametrize("working_dir", [None, "ws"])
@pytest.mark.parametrize("ref", ["absolute", "dotdot", "symlink"])
def test_at_file_stays_inside(box, working_dir, ref):
    from praisonai_code.cli.features.custom_definitions import TemplateInterpolator

    ws, outside = box
    arg = {"absolute": str(outside / "secret.txt"), "dotdot": "../outside/secret.txt",
           "symlink": "link/secret.txt"}[ref]
    wd = ws if working_dir else None
    out = TemplateInterpolator.interpolate("Review @$ARGUMENTS", arg, working_dir=wd)
    assert "CANARY-5e1d" not in out
    assert "INSIDE-OK" in TemplateInterpolator.interpolate("Review @$ARGUMENTS", "inside.txt", working_dir=wd)


@pytest.fixture
def strict(tmp_path):
    from praisonai_code.cli.features.sandbox_executor import SandboxExecutorHandler

    handler = SandboxExecutorHandler()
    handler.initialize(mode="strict", working_dir=str(tmp_path))
    return handler


def _depth_to_root():
    import tempfile
    return "../" * len(Path(os.path.realpath(tempfile.gettempdir())).parts) + "../"


@pytest.mark.parametrize("cmd", [
    "cat {up}etc/hosts",          # relative traversal out of the temp dir
    "cat '/etc/hosts'",           # quoted absolute path
    "cat \"/etc/hosts\"",
    "grep -f=/etc/hosts x",       # path after '='
])
def test_strict_mode_blocks_resolved_paths(strict, cmd):
    result = strict.execute(cmd.format(up=_depth_to_root()))
    assert result.success is False and result.policy_violations, result


def test_strict_mode_still_runs_plain_commands(strict):
    result = strict.execute("echo hello")
    assert result.success is True and "hello" in result.stdout
