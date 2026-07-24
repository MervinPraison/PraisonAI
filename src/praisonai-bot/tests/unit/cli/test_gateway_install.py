"""
Tests for gateway daemon management commands.

Tests that gateway install/uninstall/logs call daemon functions with correct args.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from praisonai_bot.cli.commands.gateway import app


@patch("praisonai_bot.daemon.install_daemon")
def test_gateway_install_success(mock_install):
    """Test successful gateway install command."""
    mock_install.return_value = {"ok": True, "message": "Installed successfully"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["install", "--config", "test.yaml"])
    
    mock_install.assert_called_once_with(config_path="test.yaml")
    assert result.exit_code == 0


@patch("praisonai_code.cli._paths.resolve_bot_config_path", return_value="bot.yaml")
@patch("praisonai_bot.daemon.install_daemon")
def test_gateway_install_failure(mock_install, mock_resolve):
    """Test failed gateway install command."""
    mock_install.return_value = {"ok": False, "error": "Installation failed"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["install"])
    
    mock_install.assert_called_once_with(config_path="bot.yaml")  # default
    assert result.exit_code == 1


@patch("praisonai_bot.daemon.uninstall_daemon")
def test_gateway_uninstall_success(mock_uninstall):
    """Test successful gateway uninstall command."""
    mock_uninstall.return_value = {"ok": True, "message": "Uninstalled successfully"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["uninstall"])
    
    mock_uninstall.assert_called_once()
    assert result.exit_code == 0


@patch("praisonai_bot.daemon.uninstall_daemon")
def test_gateway_uninstall_failure(mock_uninstall):
    """Test failed gateway uninstall command."""
    mock_uninstall.return_value = {"ok": False, "error": "Uninstallation failed"}
    
    runner = CliRunner()
    result = runner.invoke(app, ["uninstall"])
    
    mock_uninstall.assert_called_once()
    assert result.exit_code == 1


@patch("praisonai_bot.daemon._detect_platform", return_value="systemd")
@patch("praisonai_bot.daemon.systemd.get_logs")
def test_gateway_logs_systemd(mock_get_logs, mock_detect):
    """Test gateway logs command on systemd."""
    mock_get_logs.return_value = "test log output"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs", "-n", "100"])
    
    mock_get_logs.assert_called_once_with(lines=100)
    assert result.exit_code == 0


@patch("praisonai_bot.daemon._detect_platform", return_value="launchd")
@patch("praisonai_bot.daemon.launchd.get_logs")
def test_gateway_logs_launchd(mock_get_logs, mock_detect):
    """Test gateway logs command on launchd."""
    mock_get_logs.return_value = "test log output"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs"])
    
    mock_get_logs.assert_called_once_with(lines=50)  # default
    assert result.exit_code == 0


@patch("praisonai_bot.daemon._detect_platform", return_value="windows")
@patch("praisonai_bot.daemon.windows.get_logs")
def test_gateway_logs_windows(mock_get_logs, mock_detect):
    """Test gateway logs command on Windows."""
    mock_get_logs.return_value = "Log viewing not yet implemented for Windows"
    
    runner = CliRunner()
    result = runner.invoke(app, ["logs"])
    
    mock_get_logs.assert_called_once_with(lines=50)
    assert result.exit_code == 0


@patch("praisonai_bot.daemon.get_daemon_status")
@patch("praisonai_bot.cli.features.gateway.GatewayHandler")
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
    mock_handler.status.assert_called_once_with(host="127.0.0.1", port=8765, deep=False)
    assert result.exit_code == 0


def test_gateway_restart_command_registered():
    """`gateway restart` must be a first-class, discoverable command (#3161)."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "restart" in result.output


@patch("praisonai_bot.daemon.restart_daemon")
@patch("praisonai_bot.daemon.get_daemon_status")
def test_gateway_restart_daemon_aware(mock_status, mock_restart):
    """When a service is installed, restart delegates to the daemon manager."""
    mock_status.return_value = {"installed": True, "running": True, "platform": "systemd"}
    mock_restart.return_value = {"ok": True, "message": "Service restarted"}

    runner = CliRunner()
    result = runner.invoke(app, ["restart"])

    mock_restart.assert_called_once()
    assert result.exit_code == 0


@patch("praisonai_bot.cli.features.gateway.GatewayHandler")
@patch("praisonai_bot.daemon.restart_daemon")
@patch("praisonai_bot.daemon.get_daemon_status")
def test_gateway_restart_direct_when_no_daemon(mock_status, mock_restart, mock_handler_class):
    """With no installed service, restart drains + relaunches directly (#3161)."""
    mock_status.return_value = {"installed": False}
    mock_handler = MagicMock()
    mock_handler_class.return_value = mock_handler

    runner = CliRunner()
    result = runner.invoke(app, ["restart", "--config", "gateway.yaml"])

    mock_restart.assert_not_called()
    mock_handler.stop.assert_called_once()
    mock_handler.start.assert_called_once()
    assert result.exit_code == 0


def test_gateway_hooks_subcommands_registered():
    """`gateway hooks {add,list,remove}` must be discoverable (#3161)."""
    runner = CliRunner()
    result = runner.invoke(app, ["hooks", "--help"])
    assert result.exit_code == 0
    for sub in ("add", "list", "remove"):
        assert sub in result.output


@patch("praisonai_bot.cli.features.gateway.GatewayHandler")
def test_gateway_hooks_list_delegates(mock_handler_class):
    """`gateway hooks list` reuses GatewayHandler.hooks()."""
    mock_handler = MagicMock()
    mock_handler.hooks.return_value = 0
    mock_handler_class.return_value = mock_handler

    runner = CliRunner()
    result = runner.invoke(app, ["hooks", "list", "--config", "gw.yaml"])

    assert result.exit_code == 0
    mock_handler.hooks.assert_called_once()
    ns = mock_handler.hooks.call_args.args[0]
    assert ns.hooks_command == "list"
    assert ns.config_file == "gw.yaml"


@patch("praisonai_bot.cli.features.gateway.GatewayHandler")
@patch("praisonai_bot.daemon.restart_daemon")
@patch("praisonai_bot.daemon.get_daemon_status")
def test_gateway_restart_applies_drain_timeout_to_old_process(
    mock_status, mock_restart, mock_handler_class
):
    """restart --drain-timeout is passed to stop() so the OLD process gets the
    full drain window instead of a fixed 10s cut-off (#3161)."""
    mock_status.return_value = {"installed": False}
    mock_handler = MagicMock()
    mock_handler_class.return_value = mock_handler

    runner = CliRunner()
    result = runner.invoke(app, ["restart", "--drain-timeout", "45"])

    assert result.exit_code == 0
    mock_handler.stop.assert_called_once()
    assert mock_handler.stop.call_args.kwargs["drain_timeout"] == 45.0


def test_channel_control_resolves_non_default_port():
    """pause/resume/reconnect must locate a gateway on a non-default port
    instead of always probing 127.0.0.1:8765 (#3161)."""
    from praisonai_bot.cli.commands import gateway as gw

    captured = {}

    class _FakeLock:
        def __init__(self, host="127.0.0.1", port=8765):
            captured["host"] = host
            captured["port"] = port

        def get_lock_info(self):
            return {
                "is_running": True,
                "host": captured["host"],
                "port": captured["port"],
            }

    with patch(
        "praisonai_bot.gateway.port_utils.GatewayPIDLock", _FakeLock
    ):
        rest = gw._resolve_gateway_rest_url(None, host="127.0.0.1", port=9000)

    assert captured["port"] == 9000
    assert "9000" in rest


@patch("praisonai_bot.cli.commands.gateway._channel_control")
def test_gateway_pause_forwards_host_port(mock_control):
    """`gateway pause --port` forwards the endpoint to channel control."""
    runner = CliRunner()
    result = runner.invoke(app, ["pause", "telegram", "--port", "9000"])

    assert result.exit_code == 0
    mock_control.assert_called_once()
    kwargs = mock_control.call_args.kwargs
    assert kwargs["port"] == 9000


def test_windows_restart_aborts_when_end_fails():
    """Windows restart must NOT relaunch if `schtasks /End` fails, to avoid a
    duplicate/colliding gateway (#3161)."""
    from praisonai_bot.daemon import windows

    calls = []

    class _Result:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if "/Query" in cmd:
            return _Result(0, stdout=windows.TASK_NAME)
        if "/End" in cmd:
            return _Result(1, stderr="access denied")
        if "/Run" in cmd:
            return _Result(0)
        return _Result(0)

    with patch("praisonai_bot.daemon.windows.subprocess.run", side_effect=fake_run):
        result = windows.restart()

    assert result["ok"] is False
    assert not any("/Run" in c for c in calls)