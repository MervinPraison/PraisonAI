"""
Tests for the onboard CLI command.

Tests that the onboard command is properly registered and calls the wizard.
"""

import pytest
from unittest.mock import patch, MagicMock
import typer
from typer.testing import CliRunner

from praisonai.cli.commands.onboard import app


def test_onboard_command_registered():
    """Test that onboard command is registered."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "onboard" in result.output or "wizard" in result.output


@patch("praisonai.cli.features.onboard.run_onboard")
def test_onboard_calls_wizard(mock_run_onboard):
    """Test that onboard command calls run_onboard."""
    runner = CliRunner()
    result = runner.invoke(app, [])
    
    # Should call the wizard
    mock_run_onboard.assert_called_once()
    assert result.exit_code == 0


@patch("praisonai.cli.features.onboard.run_onboard")
def test_onboard_handles_keyboard_interrupt(mock_run_onboard):
    """Test that onboard handles KeyboardInterrupt gracefully."""
    mock_run_onboard.side_effect = KeyboardInterrupt()
    
    runner = CliRunner()
    result = runner.invoke(app, [])
    
    # Should exit with code 130 (standard SIGINT exit code)
    assert result.exit_code == 130