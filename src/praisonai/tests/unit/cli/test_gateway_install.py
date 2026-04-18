"""
Tests for gateway daemon management commands.

Tests that gateway install/uninstall/logs call daemon functions with correct args.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from praisonai.cli.commands.gateway import app


@patch("praisonai.daemon.install_daemon")
def test_gateway_install_success(mock_install):
    """Test successful gateway install command."""
    mock_install.return_value = {"ok": True, "message": "Installed successfully"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["install", "--config", "test.yaml"])
    
    mock_install.assert_called_once_with(config_path="test.yaml")
    assert result.exit_code == 0


@patch("praisonai.daemon.install_daemon")
def test_gateway_install_failure(mock_install):
    """Test failed gateway install command."""
    mock_install.return_value = {"ok": False, "error": "Installation failed"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["install"])
    
    mock_install.assert_called_once_with(config_path="bot.yaml")  # default
    assert result.exit_code == 1


@patch("praisonai.daemon.uninstall_daemon")
def test_gateway_uninstall_success(mock_uninstall):
    """Test successful gateway uninstall command."""
    mock_uninstall.return_value = {"ok": True, "message": "Uninstalled successfully"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["uninstall"])
    
    mock_uninstall.assert_called_once()
    assert result.exit_code == 0


@patch("praisonai.daemon.uninstall_daemon")
def test_gateway_uninstall_failure(mock_uninstall):
    """Test failed gateway uninstall command."""
    mock_uninstall.return_value = {"ok": False, "error": "Uninstallation failed"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["uninstall"])
    
    mock_uninstall.assert_called_once()
    assert result.exit_code == 1


@patch("praisonai.daemon._detect_platform", return_value="systemd")
@patch("praisonai.daemon.systemd.get_logs")
def test_gateway_logs_systemd(mock_get_logs, mock_detect):
    """Test gateway logs command on systemd."""
    mock_get_logs.return_value = "test log output"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "-n", "100"])
    
    mock_get_logs.assert_called_once_with(lines=100)
    assert result.exit_code == 0


@patch("praisonai.daemon._detect_platform", return_value="launchd")
@patch("praisonai.daemon.launchd.get_logs")
def test_gateway_logs_launchd(mock_get_logs, mock_detect):
    """Test gateway logs command on launchd."""
    mock_get_logs.return_value = "test log output"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs"])
    
    mock_get_logs.assert_called_once_with(lines=50)  # default
    assert result.exit_code == 0


@patch("praisonai.daemon._detect_platform", return_value="windows")
@patch("praisonai.daemon.windows.get_logs")
def test_gateway_logs_windows(mock_get_logs, mock_detect):
    """Test gateway logs command on Windows."""
    mock_get_logs.return_value = "Log viewing not yet implemented for Windows"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs"])
    
    mock_get_logs.assert_called_once_with(lines=50)
    assert result.exit_code == 0


@patch("praisonai.daemon.get_daemon_status")
@patch("praisonai.cli.features.gateway.GatewayHandler")
def test_gateway_status_with_daemon(mock_handler_class, mock_status):
    """Test gateway status command includes daemon status."""
    mock_status.return_value = {
        "installed": True, 
        "running": True, 
        "platform": "systemd"
    }
    mock_handler = MagicMock()
    mock_handler_class.return_value = mock_handler
    
    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    
    mock_status.assert_called_once()
    mock_handler.status.assert_called_once_with(host="127.0.0.1", port=8765)
    assert result.exit_code == 0