"""Tests for dashboard (unified) CLI command flags and aiui behavior."""

import sys
import inspect
from unittest.mock import MagicMock, patch

from rich.console import Console

from praisonai.cli.commands.dashboard import _run_aiui_dashboard, unified


def test_unified_command_has_new_flags():
    """unified command should expose auto_start and aiui flags."""
    params = inspect.signature(unified).parameters
    assert "auto_start" in params
    assert "aiui" in params


def test_run_aiui_dashboard_returns_false_when_aiui_missing():
    """Should fail gracefully when aiui integration dependencies are missing."""
    console = Console()
    with patch.dict(sys.modules, {"uvicorn": None}):
        assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False


def test_run_aiui_dashboard_returns_false_on_subprocess_failure():
    """Should fail gracefully when in-process host startup fails."""
    console = Console()
    mock_app = MagicMock()
    with patch("uvicorn.run", side_effect=RuntimeError("host failed")):
        with patch("praisonai.integration.host_app.build_host_app", return_value=mock_app):
            assert _run_aiui_dashboard(3000, "127.0.0.1", console) is False
