"""Tests for port management CLI command.

TDD tests for praisonai port command:
- port list: List all processes using ports
- port check <port>: Check if specific port is in use
- port kill <port>: Kill process using specific port
- port conflict detection in other commands
"""

import pytest
from unittest.mock import patch, MagicMock


class TestPortCommand:
    """Tests for port management CLI commands."""

    def test_port_command_imports(self):
        """Test that port command module can be imported."""
        from praisonai.cli.commands.port import app
        assert app is not None

    def test_port_list_command_exists(self):
        """Test that port list subcommand exists."""
        from praisonai.cli.commands.port import app

        # Get registered commands
        commands = app.registered_commands
        command_names = [cmd.name for cmd in commands]

        # Should have list, check, kill commands
        assert "list" in command_names or any("list" in str(cmd) for cmd in commands)

    def test_port_check_command_exists(self):
        """Test that port check subcommand exists."""
        from praisonai.cli.commands.port import app

        commands = app.registered_commands
        command_names = [cmd.name for cmd in commands]
        assert "check" in command_names or any("check" in str(cmd) for cmd in commands)

    def test_port_kill_command_exists(self):
        """Test that port kill subcommand exists."""
        from praisonai.cli.commands.port import app

        commands = app.registered_commands
        command_names = [cmd.name for cmd in commands]
        assert "kill" in command_names or any("kill" in str(cmd) for cmd in commands)


class TestPortUtils:
    """Tests for port utility functions."""

    def test_get_process_using_port_linux_darwin(self):
        """Test getting process info using lsof on Linux/macOS."""
        import sys
        from praisonai.cli.commands.port import _get_process_using_port

        # Save original platform
        original_platform = sys.platform
        try:
            # Mock linux platform by modifying sys directly
            sys.platform = 'linux'
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=(
                        "COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
                        "redis-ser 1234 user 4u IPv6 0x123 0t0 TCP *:6379 (LISTEN)\n"
                    )
                )

                result = _get_process_using_port(6379)

                assert result is not None
                assert result['port'] == 6379
                assert result['pid'] == '1234'
                assert 'redis' in result['name'].lower()
        finally:
            # Restore original platform
            sys.platform = original_platform

    def test_get_process_using_port_not_found(self):
        """Test getting process when port is not in use."""
        from praisonai.cli.commands.port import _get_process_using_port

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            result = _get_process_using_port(9999)

            assert result is None

    def test_kill_process_by_pid_success(self):
        """Test killing process by PID."""
        from praisonai.cli.commands.port import _kill_process

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = _kill_process(1234, force=False)

            assert result is True
            mock_run.assert_called_once()

    def test_kill_process_force_flag(self):
        """Test killing process with force flag uses SIGKILL."""
        from praisonai.cli.commands.port import _kill_process

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = _kill_process(1234, force=True)

            assert result is True
            # Should use -9 for force kill
            call_args = mock_run.call_args[0][0]
            assert '-9' in call_args or '/F' in call_args


class TestPortConflictDetection:
    """Tests for port conflict detection in other commands."""

    def test_is_port_conflict_error_redis(self):
        """Test detecting Redis port conflict in error message."""
        from praisonai.cli.commands.port import _is_port_conflict_error, _extract_port_from_error

        error_msg = "Ports are not available: exposing port TCP 127.0.0.1:6379 -> 0.0.0.0:0: listen tcp 127.0.0.1:6379: bind: address already in use"

        assert _is_port_conflict_error(error_msg) is True
        assert _extract_port_from_error(error_msg) == 6379

    def test_is_port_conflict_error_generic(self):
        """Test detecting generic port conflict."""
        from praisonai.cli.commands.port import _is_port_conflict_error

        error_msg = "bind: address already in use"
        assert _is_port_conflict_error(error_msg) is True

    def test_is_not_port_conflict_error(self):
        """Test that non-port errors return False."""
        from praisonai.cli.commands.port import _is_port_conflict_error

        error_msg = "Container failed to start: permission denied"
        assert _is_port_conflict_error(error_msg) is False

    def test_show_port_conflict_help(self):
        """Test showing helpful message for port conflicts."""
        from praisonai.cli.commands.port import _show_port_conflict_help

        with patch('rich.console.Console.print') as mock_print:
            _show_port_conflict_help(6379)

            # Should show help message with commands to resolve
            calls = mock_print.call_args_list
            help_text = ' '.join([str(call) for call in calls])
            assert '6379' in help_text


class TestPortIntegration:
    """Integration tests for port commands."""

    @pytest.mark.slow
    def test_port_list_shows_table(self):
        """Test port list shows formatted table."""
        from praisonai.cli.commands.port import _get_all_ports

        with patch('subprocess.run') as mock_run:
            # Mock lsof output with multiple ports
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=(
                    "COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
                    "redis-ser 1234 user 4u IPv6 0x123 0t0 TCP *:6379 (LISTEN)\n"
                    "postgres  5678 user 5u IPv6 0x456 0t0 TCP *:5432 (LISTEN)\n"
                )
            )

            # Call the underlying function
            processes = _get_all_ports()

            # Should return list of processes
            assert len(processes) > 0
            # Check for expected ports
            ports = [p['port'] for p in processes]
            assert 6379 in ports
            assert 5432 in ports

    def test_port_kill_with_confirmation(self):
        """Test port kill asks for confirmation."""
        from praisonai.cli.commands.port import port_kill
        from rich.console import Console
        import typer

        console = Console()

        with patch('praisonai.cli.commands.port._get_process_using_port') as mock_get:
            mock_get.return_value = {
                'port': 6379,
                'pid': '1234',
                'name': 'redis-server',
                'user': 'user'
            }

            with patch('typer.confirm') as mock_confirm:
                mock_confirm.return_value = False  # User says no

                with patch.object(console, 'print'):
                    # Should exit with 0 because user declined
                    with pytest.raises(typer.Exit) as exc_info:
                        port_kill(port=6379, force=False, yes=False, json_output=False)

                    assert exc_info.value.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
