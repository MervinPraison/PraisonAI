"""Tests for dashboard (unified) CLI command flags and aiui behavior."""

import inspect
import subprocess
from unittest.mock import MagicMock, patch

from rich.console import Console

from praisonai.cli.commands.unified import _run_aiui_dashboard, unified


def test_unified_command_has_new_flags():
    """unified command should expose auto_start and aiui flags."""
    params = inspect.signature(unified).parameters
    assert "auto_start" in params
    assert "aiui" in params


def test_run_aiui_dashboard_returns_false_when_aiui_missing():
    """Should fail gracefully when praisonaiui import check fails."""
    console = Console()
    with patch("subprocess.run", return_value=MagicMock(returncode=1)):
        assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False


def test_run_aiui_dashboard_returns_false_on_subprocess_failure():
    """Should fail gracefully when aiui subprocess exits non-zero."""
    console = Console()
    with patch.object(console, "print") as mock_print:
        with patch(
            "subprocess.run",
            side_effect=[
                MagicMock(returncode=0),
                subprocess.CalledProcessError(1, ["python", "temp_script.py"]),
            ],
        ):
            assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False
    printed_messages = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("exited with code 1" in message for message in printed_messages)
