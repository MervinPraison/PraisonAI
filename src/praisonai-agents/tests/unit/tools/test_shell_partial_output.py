"""Timeout/interrupt keep output printed before the cut-off (issue #5990)."""

import sys
import threading

import pytest

from praisonaiagents.tools.shell_tools import ShellTools


@pytest.fixture(autouse=True)
def _auto_approve(monkeypatch):
    # execute_command is approval-gated (critical); auto-approve for the test.
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")

_SCRIPT = (
    "import time,sys;print('step1 ok',flush=True);"
    "print('warn: x',file=sys.stderr,flush=True);time.sleep(30)"
)


def _cmd():
    return f'{sys.executable} -c "{_SCRIPT}"'


def test_timeout_keeps_partial_output():
    result = ShellTools().execute_command(_cmd(), timeout=2)
    assert result["success"] is False
    assert result["timed_out"] is True
    assert "step1 ok" in result["stdout"]
    assert "warn: x" in result["stderr"]
    assert result["stderr"].endswith("Command timed out after 2 seconds")


def test_interrupt_keeps_partial_output(monkeypatch):
    cancel = threading.Event()
    tools = ShellTools()
    monkeypatch.setattr(tools, "_current_cancel_event", lambda: cancel)
    threading.Timer(1.5, cancel.set).start()
    result = tools.execute_command(_cmd(), timeout=20)
    assert result["interrupted"] is True
    assert "step1 ok" in result["stdout"]
    assert result["stderr"].endswith("Command interrupted by user")


def test_timeout_keeps_unterminated_line():
    # Flushed text without a trailing newline must survive the timeout too.
    script = "import time,sys;sys.stdout.write('progress');sys.stdout.flush();time.sleep(30)"
    result = ShellTools().execute_command(f'{sys.executable} -c "{script}"', timeout=2)
    assert result["timed_out"] is True
    assert "progress" in result["stdout"]
