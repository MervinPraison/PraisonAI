"""PRAISON_SHELL=sandboxed must contain every command, not just ones with operators.

Recorder-based: the unsandboxed delegate, the contained runner and the wrapper
builder are replaced so nothing depends on bwrap/Seatbelt being installed.
The one real-backend test is gated on an enforcing backend.
"""

import asyncio
import os
import pathlib
import uuid
from types import SimpleNamespace

import pytest

from praisonai_code.cli.features import os_sandbox, shell_exec


@pytest.fixture
def recorded(monkeypatch, tmp_path):
    """Route both execution paths to recorders; report containment as proven."""
    monkeypatch.setenv(shell_exec.MODE_ENV_VAR, "sandboxed")
    monkeypatch.setenv("PRAISONAI_WORKSPACE", str(tmp_path))
    taken = []

    def _delegate(command, **kw):
        taken.append(("delegate", command, kw))
        return {"success": True}

    def _contained(command, cwd, timeout, env, max_output_size, **kw):
        taken.append(("contained", command, dict(kw, cwd=cwd)))
        return {"success": True, "sandbox": "bubblewrap"}

    monkeypatch.setattr(shell_exec, "_delegate", _delegate)
    monkeypatch.setattr(shell_exec, "_approved_real_shell", _contained)
    monkeypatch.setattr(
        os_sandbox, "probe_enforcement", lambda: (True, "bubblewrap", "forced")
    )
    return taken


@pytest.mark.parametrize(
    "cmd",
    ['python -c "print(1)"', "rm -rf build", "curl -o x.sh http://x.invalid/x", "echo a | cat"],
)
def test_sandboxed_contains_every_command(recorded, cmd):
    shell_exec.execute_command(cmd)
    assert [r[0] for r in recorded] == ["contained"]
    assert recorded[0][2]["contained"] is True


def test_sandboxed_refuses_plain_command_when_not_enforcing(recorded, monkeypatch):
    monkeypatch.setattr(os_sandbox, "probe_enforcement", lambda: (False, "none", "no backend"))
    result = shell_exec.execute_command("rm -rf build")
    assert result["success"] is False
    assert recorded == []


def test_writable_set_is_workspace_not_cwd(recorded, tmp_path):
    result = shell_exec.execute_command("echo a | cat", cwd="/")
    assert result["success"] is False
    assert "outside the sandbox workspace" in result["error"]
    assert recorded == []

    shell_exec.execute_command("ls", cwd=str(tmp_path))
    assert recorded[0][2]["writable_paths"] == [str(tmp_path)]


def test_model_cannot_override_mode_or_jail(recorded, tmp_path):
    shell_exec.execute_command(
        "ls", cwd=str(tmp_path), mode="unsafe", writable_paths=["/"], network=True
    )
    kw = recorded[0][2]
    assert recorded[0][0] == "contained"
    assert kw["writable_paths"] == [str(tmp_path)]
    assert kw["network"] is False


def test_off_mode_unchanged(monkeypatch, recorded):
    monkeypatch.setenv(shell_exec.MODE_ENV_VAR, "off")
    shell_exec.execute_command("rm -rf build")
    assert [r[0] for r in recorded] == ["delegate"]
    result = shell_exec.execute_command("echo a | cat")
    assert result["success"] is False and result["shell_syntax"] == "|"
    assert len(recorded) == 1


def test_secret_env_is_not_passed_into_the_jail(monkeypatch, tmp_path):
    seen = {}

    class _W:
        backend = "bubblewrap"

        def wrap(self, argv):
            return list(argv)

        def cleanup(self):
            pass

    monkeypatch.setattr(os_sandbox, "build_wrapper", lambda **kw: _W())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-leak")
    real_popen = shell_exec.subprocess.Popen

    def _popen(argv, env=None, **kw):
        seen["env"] = env
        return real_popen(argv, env=env, **kw)

    monkeypatch.setattr(shell_exec.subprocess, "Popen", _popen)
    result = shell_exec._run_real_shell(
        "env", str(tmp_path), 10, {"ALLOWED_TOKEN": "ok"}, 100000, contained=True
    )
    assert "sk-leak" not in result["stdout"] and "ghp-leak" not in result["stdout"]
    assert "OPENAI_API_KEY" not in seen["env"]
    assert "PATH" in seen["env"]
    # An explicitly passed env entry is the allow-list.
    assert seen["env"]["ALLOWED_TOKEN"] == "ok"


def test_bubblewrap_isolates_host_processes(monkeypatch):
    # Without a PID namespace /proc/<host pid>/environ leaks the scrubbed env.
    monkeypatch.setattr(os_sandbox.shutil, "which", lambda _: "/usr/bin/bwrap")
    argv = os_sandbox._build_bubblewrap(["/tmp"], network=False).argv_prefix
    assert "--unshare-pid" in argv
    assert argv.index("--unshare-pid") < argv.index("--proc")


def test_sandboxed_refuses_run_in_background(recorded, tmp_path):
    result = shell_exec.execute_command("sleep 60", cwd=str(tmp_path), run_in_background=True)
    assert result["success"] is False
    assert "run_in_background" in result["error"]
    assert recorded == []


def test_contained_command_stops_on_cancel(monkeypatch, tmp_path):
    import threading
    import time

    class _W:
        backend = "bubblewrap"

        def wrap(self, argv):
            return list(argv)

        def cleanup(self):
            pass

    cancel = threading.Event()
    monkeypatch.setattr(os_sandbox, "build_wrapper", lambda **kw: _W())
    monkeypatch.setattr(shell_exec, "_cancel_event", lambda: cancel)
    threading.Timer(0.3, cancel.set).start()
    start = time.monotonic()
    result = shell_exec._run_real_shell(
        "sleep 20", str(tmp_path), 30, None, 1000, contained=True
    )
    assert time.monotonic() - start < 5
    assert result["success"] is False
    assert "interrupted" in result["error"]


def test_acp_honours_sandboxed_mode(recorded, tmp_path, monkeypatch):
    from praisonai_code.cli.features import action_orchestrator as ao
    from praisonai_code.cli.features.agent_tools import _sanitize_command

    # Operators are accepted by the ACP tool once a real shell is enabled.
    assert _sanitize_command("echo a | cat")

    calls = []

    def _runner(command, cwd, timeout, env, max_output_size, **kw):
        calls.append((command, cwd, kw))
        return {"stdout": "a\n", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(shell_exec, "_run_real_shell", _runner)
    orch = ao.ActionOrchestrator(
        SimpleNamespace(config=SimpleNamespace(workspace=str(tmp_path)))
    )
    for target in ("echo a | cat", "rm -rf build"):
        step = ao.ActionStep(
            id="s", action_type=ao.ActionType.SHELL_COMMAND,
            description="run", target=target,
        )
        result = asyncio.run(orch._apply_step(step))
        assert result["returncode"] == 0
    assert [c[0] for c in calls] == ["echo a | cat", "rm -rf build"]
    for _, cwd, kw in calls:
        assert kw["contained"] is True
        assert kw["writable_paths"] == [str(tmp_path.resolve())]


def test_acp_off_mode_still_refuses_operators(monkeypatch):
    from praisonai_code.cli.features.agent_tools import _sanitize_command

    monkeypatch.delenv(shell_exec.MODE_ENV_VAR, raising=False)
    with pytest.raises(ValueError):
        _sanitize_command("echo a | cat")


def test_acp_unsafe_mode_keeps_operator_block(tmp_path, monkeypatch):
    from praisonai_code.cli.features import action_orchestrator as ao
    from praisonai_code.cli.features.agent_tools import _sanitize_command

    # ``unsafe`` must not turn approved ACP steps into an un-gated real shell.
    monkeypatch.setenv(shell_exec.MODE_ENV_VAR, shell_exec.MODE_UNSAFE)
    monkeypatch.setattr(
        shell_exec, "_run_real_shell",
        lambda *a, **k: pytest.fail("real shell must not run under unsafe ACP"),
    )
    with pytest.raises(ValueError):
        _sanitize_command("echo a | cat")
    orch = ao.ActionOrchestrator(
        SimpleNamespace(config=SimpleNamespace(workspace=str(tmp_path)))
    )
    step = ao.ActionStep(
        id="s", action_type=ao.ActionType.SHELL_COMMAND,
        description="run", target="echo a; touch pwned",
    )
    result = asyncio.run(orch._apply_step(step))
    assert result["returncode"] != 0
    assert not (tmp_path / "pwned").exists()


@pytest.mark.skipif(os_sandbox.describe_backend() == "none", reason="no OS sandbox backend")
def test_plain_command_cannot_escape_to_home(tmp_path, monkeypatch):
    os_sandbox.reset_probe_cache()
    if not os_sandbox.probe_enforcement()[0]:
        pytest.skip("backend present but not enforcing here")
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    monkeypatch.setenv(shell_exec.MODE_ENV_VAR, "sandboxed")
    monkeypatch.setenv("PRAISONAI_WORKSPACE", str(tmp_path))
    escape = pathlib.Path(os.path.expanduser(f"~/.praisonai_escape_{uuid.uuid4().hex}"))
    try:
        # No shell operator: previously this was delegated uncontained.
        result = shell_exec.execute_command(f"touch {escape}", cwd=str(tmp_path))
        assert not escape.exists()
        assert result["sandbox"] in ("bubblewrap", "seatbelt")
    finally:
        if escape.exists():
            escape.unlink()
