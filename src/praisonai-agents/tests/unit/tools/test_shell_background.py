"""Tests for non-blocking background commands in shell_tools (issue #5799)."""

import platform
import sys
import time

import pytest

from praisonaiagents.tools.shell_tools import ShellTools

pytestmark = pytest.mark.skipif(platform.system() == "Windows", reason="POSIX process groups")


@pytest.fixture(autouse=True)
def _auto_approve(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")


def _run(tools, command, **kwargs):
    return tools.execute_command(command, **kwargs)


def _wait_exit(tools, process_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = tools.get_command_output(process_id)
        if result["status"] == "exited":
            return result
        time.sleep(0.05)
    raise AssertionError("background command did not exit")


def test_background_returns_immediately_and_captures_output():
    tools = ShellTools()
    start = time.monotonic()
    result = _run(tools, f'{sys.executable} -c "import time; print(\'hello\', flush=True); time.sleep(0.3)"',
                  run_in_background=True)
    assert time.monotonic() - start < 2
    assert result["success"] is True
    assert result["status"] == "running"
    assert result["pid"] > 0

    final = _wait_exit(tools, result["process_id"])
    assert final["exit_code"] == 0
    assert final["success"] is True
    assert "hello" in final["output"]


def test_background_ignores_timeout_and_can_be_stopped():
    tools = ShellTools()
    result = _run(tools, f'{sys.executable} -c "import time; time.sleep(60)"',
                  timeout=1, run_in_background=True)
    time.sleep(1.2)
    assert tools.get_command_output(result["process_id"])["status"] == "running"

    stopped = tools.stop_command(result["process_id"])
    assert stopped["success"] is True
    assert stopped["status"] == "exited"
    assert tools.get_command_output(result["process_id"])["status"] == "exited"


def test_output_tail_is_bounded():
    tools = ShellTools()
    result = _run(tools, f'{sys.executable} -c "[print(i) for i in range(50)]"', run_in_background=True)
    final = _wait_exit(tools, result["process_id"])
    lines = tools.get_command_output(result["process_id"], tail=3)["output"].splitlines()
    assert final["exit_code"] == 0
    assert lines == ["47", "48", "49"]


def test_nonzero_exit_reports_failure():
    tools = ShellTools()
    result = _run(tools, f'{sys.executable} -c "import sys; sys.exit(3)"', run_in_background=True)
    final = _wait_exit(tools, result["process_id"])
    assert final["exit_code"] == 3
    assert final["success"] is False


def test_unknown_process_id():
    tools = ShellTools()
    assert tools.get_command_output("missing")["success"] is False
    assert tools.stop_command("missing")["success"] is False


def test_shell_syntax_still_refused_in_background():
    tools = ShellTools()
    result = _run(tools, "echo hi > out.txt", run_in_background=True)
    assert result["success"] is False
    assert "process_id" not in result


def test_exported_from_tools_package():
    from praisonaiagents import tools

    assert callable(tools.get_command_output)
    assert callable(tools.stop_command)


def _pid_alive(pid):
    """True if *pid* is running; a dead-but-unreaped zombie counts as stopped."""
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        pass
    try:
        import psutil
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return True


def test_stop_kills_children_that_ignore_sigterm(tmp_path):
    """Parent exits on SIGTERM; a child ignoring it must still be killed."""
    pid_file = tmp_path / "child.pid"
    # The child writes its pid only after SIG_IGN is installed, so the test
    # cannot race ahead and stop the group before SIGTERM is being ignored.
    child = (
        "import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    )
    script = tmp_path / "parent.py"
    script.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        "time.sleep(60)\n"
    )
    tools = ShellTools()
    result = _run(tools, f"{sys.executable} {script}", run_in_background=True)
    deadline = time.monotonic() + 10
    while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
        time.sleep(0.05)
    child_pid = int(pid_file.read_text())

    assert tools.stop_command(result["process_id"])["status"] == "exited"
    deadline = time.monotonic() + 5
    while _pid_alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    if _pid_alive(child_pid):
        pytest.fail("child process survived stop_command")


@pytest.mark.parametrize("error", [FileNotFoundError("taskkill"), __import__("subprocess").TimeoutExpired("taskkill", 10)])
def test_kill_tree_windows_without_psutil_still_kills_when_taskkill_fails(monkeypatch, error):
    """A missing or hung taskkill must not skip process.kill() (no psutil, Windows)."""
    from unittest import mock

    from praisonaiagents.tools import shell_tools

    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    monkeypatch.setattr(shell_tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(shell_tools.subprocess, "run", mock.Mock(side_effect=error))
    process = mock.Mock(pid=12345)

    ShellTools()._kill_process_tree(process)

    shell_tools.subprocess.run.assert_called_once()
    process.kill.assert_called_once()
