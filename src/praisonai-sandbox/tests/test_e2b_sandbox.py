"""
Unit tests for E2B sandbox implementation.

These tests mock the ``e2b_code_interpreter`` SDK so they run without the
optional dependency or network access. They exercise the real ``E2BSandbox``
lifecycle, execution, filesystem, status, and cleanup code paths.
"""

import os
from unittest.mock import Mock, patch

import pytest

from praisonai_sandbox.e2b import E2BSandbox
from praisonaiagents.sandbox import SandboxConfig, SandboxStatus


def _available(value: bool):
    """Patch the ``is_available`` property on the E2BSandbox class."""
    return patch.object(
        type(E2BSandbox()), "is_available", property(lambda self: value)
    )


class TestE2BSandbox:
    """Test E2B sandbox implementation."""

    def test_init_default(self):
        """Test initialization with defaults."""
        sandbox = E2BSandbox()
        assert sandbox.config is not None
        assert sandbox.sandbox_type == "e2b"
        assert not sandbox._is_running

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = SandboxConfig.e2b()
        sandbox = E2BSandbox(config)
        assert sandbox.config == config

    @patch.dict(os.environ, {"E2B_API_KEY": "test-key"})
    @patch('importlib.import_module')
    def test_is_available_true(self, mock_import):
        """Test is_available returns True when E2B is properly set up."""
        sandbox = E2BSandbox()
        assert sandbox.is_available is True

    def test_is_available_no_api_key(self):
        """Test is_available returns False without API key."""
        with patch.dict(os.environ, {}, clear=True):
            sandbox = E2BSandbox()
            assert sandbox.is_available is False

    @patch('importlib.import_module', side_effect=ImportError())
    def test_is_available_no_module(self, mock_import):
        """Test is_available returns False without module."""
        sandbox = E2BSandbox()
        assert sandbox.is_available is False

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"E2B_API_KEY": "test-key"})
    async def test_start_success(self):
        """Test successful sandbox start."""
        mock_instance = Mock()
        mock_sandbox_class = Mock(return_value=mock_instance)
        mock_module = Mock(Sandbox=mock_sandbox_class)

        sandbox = E2BSandbox()

        with _available(True):
            with patch.dict('sys.modules', {'e2b_code_interpreter': mock_module}):
                await sandbox.start()

        assert sandbox._is_running
        assert sandbox._sandbox is mock_instance
        mock_sandbox_class.assert_called_once_with(api_key="test-key")

    @pytest.mark.asyncio
    async def test_start_not_available(self):
        """Test start when not available."""
        sandbox = E2BSandbox()

        with _available(False):
            with pytest.raises(RuntimeError, match="E2B is not available"):
                await sandbox.start()

    @pytest.mark.asyncio
    async def test_start_no_api_key(self):
        """Test start without API key raises ValueError."""
        mock_module = Mock(Sandbox=Mock())
        sandbox = E2BSandbox()

        with patch.dict(os.environ, {}, clear=True):
            with _available(True):
                with patch.dict('sys.modules', {'e2b_code_interpreter': mock_module}):
                    with pytest.raises(ValueError, match="E2B_API_KEY"):
                        await sandbox.start()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test start when already running is a no-op."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        await sandbox.start()  # Should not raise or do anything

    @pytest.mark.asyncio
    async def test_stop_success(self):
        """Test successful sandbox stop kills the underlying VM."""
        mock_sandbox = Mock()

        sandbox = E2BSandbox()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True

        await sandbox.stop()

        assert not sandbox._is_running
        assert sandbox._sandbox is None
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_with_error(self):
        """Test stop swallows cleanup errors."""
        mock_sandbox = Mock()
        mock_sandbox.kill.side_effect = Exception("Kill failed")

        sandbox = E2BSandbox()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True

        await sandbox.stop()  # Should not raise

        assert not sandbox._is_running

    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        """Test Python code execution."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_result = Mock()
        mock_result.text = "Hello, World!"
        mock_execution = Mock()
        mock_execution.results = [mock_result]
        mock_execution.error = None

        mock_e2b = Mock()
        mock_e2b.run_code.return_value = mock_execution
        sandbox._sandbox = mock_e2b

        result = await sandbox.execute("print('Hello, World!')", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_python_code_with_error(self):
        """Test Python code execution with error."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_error = Mock()
        mock_error.traceback = "Traceback: error"
        mock_execution = Mock()
        mock_execution.results = []
        mock_execution.error = mock_error

        mock_e2b = Mock()
        mock_e2b.run_code.return_value = mock_execution
        sandbox._sandbox = mock_e2b

        result = await sandbox.execute("invalid code", language="python")

        assert result.status == SandboxStatus.FAILED
        assert result.exit_code == 1
        assert "Traceback: error" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_bash_command(self):
        """Test bash command execution."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_command_result = Mock()
        mock_command_result.exit_code = 0
        mock_command_result.stdout = "command output"
        mock_command_result.stderr = ""

        mock_e2b = Mock()
        mock_e2b.commands.run.return_value = mock_command_result
        sandbox._sandbox = mock_e2b

        result = await sandbox.execute("echo hello", language="bash")

        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "command output"

    @pytest.mark.asyncio
    async def test_execute_bash_command_with_env_and_workdir(self):
        """Test bash command with environment and working directory (quoting)."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_command_result = Mock()
        mock_command_result.exit_code = 0
        mock_command_result.stdout = "output"
        mock_command_result.stderr = ""

        mock_e2b = Mock()
        mock_e2b.commands.run.return_value = mock_command_result
        sandbox._sandbox = mock_e2b

        env = {"TEST_VAR": "test value with spaces"}
        working_dir = "/path with spaces"

        result = await sandbox.execute(
            "echo $TEST_VAR",
            language="bash",
            env=env,
            working_dir=working_dir,
        )

        assert result.status == SandboxStatus.COMPLETED
        # export/cd/command are quoted via shlex — verify they were issued.
        issued = [c.args[0] for c in mock_e2b.commands.run.call_args_list]
        assert any("export" in cmd and "TEST_VAR" in cmd for cmd in issued)
        assert any(cmd.startswith("cd ") for cmd in issued)

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execution timeout handling maps to TIMEOUT status."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        mock_e2b.commands.run.side_effect = Exception("timeout occurred")
        sandbox._sandbox = mock_e2b

        result = await sandbox.execute("sleep 100", language="bash")

        assert result.status == SandboxStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_write_file(self):
        """Test writing file to sandbox."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        sandbox._sandbox = mock_e2b

        success = await sandbox.write_file("/test.txt", "content")

        assert success is True
        mock_e2b.files.write.assert_called_once_with("/test.txt", "content")

    @pytest.mark.asyncio
    async def test_write_file_error(self):
        """Test writing file with error returns False."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        mock_e2b.files.write.side_effect = Exception("Write failed")
        sandbox._sandbox = mock_e2b

        success = await sandbox.write_file("/test.txt", "content")

        assert success is False

    @pytest.mark.asyncio
    async def test_read_file(self):
        """Test reading file from sandbox."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        mock_e2b.files.read.return_value = "file content"
        sandbox._sandbox = mock_e2b

        content = await sandbox.read_file("/test.txt")

        assert content == "file content"

    @pytest.mark.asyncio
    async def test_read_file_error(self):
        """Test reading file with error returns None."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        mock_e2b.files.read.side_effect = Exception("Read failed")
        sandbox._sandbox = mock_e2b

        content = await sandbox.read_file("/test.txt")

        assert content is None

    @pytest.mark.asyncio
    async def test_list_files(self):
        """Test listing files in sandbox."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_command_result = Mock()
        mock_command_result.exit_code = 0
        mock_command_result.stdout = "/file1.txt\n/file2.py\n"
        mock_command_result.stderr = ""

        mock_e2b = Mock()
        mock_e2b.commands.run.return_value = mock_command_result
        sandbox._sandbox = mock_e2b

        files = await sandbox.list_files("/")

        assert files == ["/file1.txt", "/file2.py"]

    @pytest.mark.asyncio
    async def test_list_files_error(self):
        """Test listing files with error returns empty list."""
        sandbox = E2BSandbox()
        sandbox._is_running = True

        mock_e2b = Mock()
        mock_e2b.commands.run.side_effect = Exception("List failed")
        sandbox._sandbox = mock_e2b

        files = await sandbox.list_files("/")

        assert files == []

    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = E2BSandbox()

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with _available(True):
                status = sandbox.get_status()

        assert status["available"] is True
        assert status["type"] == "e2b"
        assert status["running"] is False
        assert status["api_key_set"] is True

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test sandbox cleanup does not raise."""
        sandbox = E2BSandbox()
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test sandbox reset calls stop then start."""
        sandbox = E2BSandbox()

        with patch.object(sandbox, 'stop') as mock_stop:
            with patch.object(sandbox, 'start') as mock_start:
                await sandbox.reset()

        mock_stop.assert_called_once()
        mock_start.assert_called_once()
