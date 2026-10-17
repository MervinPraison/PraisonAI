"""Regression tests for issue #5870: observer isolation, atomic state writes, git deadlines."""
import asyncio
import json
import subprocess

import pytest

from praisonaiagents import main as _main
from praisonaiagents.approval import PermissionAllowlist


def test_raising_sync_callback_does_not_propagate():
    def boom(**kw):
        raise RuntimeError("callback bug")

    _main.register_display_callback("interaction", boom)
    _main.execute_sync_callback("interaction", message="hi")  # must not raise


def test_raising_callbacks_do_not_propagate_async():
    seen = []

    def boom(**kw):
        raise RuntimeError("sync bug")

    async def aboom(message):
        seen.append(message)
        raise RuntimeError("async bug")

    _main.register_display_callback("interaction", boom)
    _main.register_display_callback("interaction", aboom, is_async=True)
    asyncio.run(_main.execute_callback("interaction", message="hi", extra=1))
    assert seen == ["hi"]


def test_allowlist_failed_save_keeps_previous_file(tmp_path):
    p = str(tmp_path / "allow.json")
    a = PermissionAllowlist()
    a.add_tool("read_file", paths=["/ok"])
    a.save(p)
    good = open(p).read()

    a._tools["read_file"].allowed_paths = ["/ok", object()]
    with pytest.raises(TypeError):
        a.save(p)
    assert open(p).read() == good
    assert PermissionAllowlist.load(p).list_tools() == ["read_file"]


def test_allowlist_load_quarantines_corrupt_file(tmp_path):
    p = tmp_path / "allow.json"
    p.write_text('{"tools": {')
    assert PermissionAllowlist.load(str(p)).list_tools() == []
    assert not p.exists()
    assert list(tmp_path.glob("allow.json.*.corrupt"))


def test_git_fetch_timeout_falls_back_to_cache(tmp_path, monkeypatch):
    from praisonaiagents.skills import remote

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    src = remote.GitRemoteSkillSource("http://127.0.0.1:1/org/skills.git")
    assert src.fetch(tmp_path) == []
    assert calls[0]["timeout"] == remote._GIT_TIMEOUT
    assert calls[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"
