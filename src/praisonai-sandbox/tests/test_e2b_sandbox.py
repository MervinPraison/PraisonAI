"""
Unit tests for E2B sandbox implementation.
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, patch
from praisonai_sandbox.e2b import E2BSandbox
from praisonaiagents.sandbox import SandboxConfig, SandboxResult, SandboxStatus


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

    @patch.dict(os.environ, {"E2B_API_KEY": "test-key"})
    @patch('e2b_code_interpreter.Sandbox')
    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_start_success(self, mock_sandbox_class):
        """Test successful sandbox start."""
        mock_instance = Mock()
        mock_sandbox_class.return_value = mock_instance
        
        sandbox = E2BSandbox()
        
        with patch.object(sandbox, 'is_available', True):
            await sandbox.start()
        
        assert sandbox._is_running
        assert sandbox._sandbox == mock_instance
        mock_sandbox_class.assert_called_once_with(api_key="test-key")

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_start_not_available(self):
        """Test start when not available."""
        sandbox = E2BSandbox()
        
        with patch.object(sandbox, 'is_available', False):
            with pytest.raises(RuntimeError, match="E2B is not available"):
                await sandbox.start()

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_start_no_api_key(self):
        """Test start without API key."""
        sandbox = E2BSandbox()
        
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sandbox, 'is_available', True):
                with pytest.raises(ValueError, match="E2B_API_KEY"):
                    await sandbox.start()

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_start_already_running(self):
        """Test start when already running."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        
        await sandbox.start()  # Should not raise or do anything

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_stop_success(self):
        """Test successful sandbox stop."""
        mock_sandbox = Mock()
        
        sandbox = E2BSandbox()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor.return_value = mock_executor
            
            await sandbox.stop()
        
        assert not sandbox._is_running
        assert sandbox._sandbox is None

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_stop_with_error(self):
        """Test stop with cleanup error."""
        mock_sandbox = Mock()
        mock_sandbox.kill.side_effect = Exception("Kill failed")
        
        sandbox = E2BSandbox()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = Exception("Kill failed")
            
            await sandbox.stop()  # Should not raise
        
        assert not sandbox._is_running

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_execute_python_code(self):
        """Test Python code execution."""
        sandbox = E2BSandbox()
        sandbox._is_running = False
        
        mock_execution = Mock()
        mock_result = Mock()
        mock_result.text = "Hello, World!"
        mock_execution.results = [mock_result]
        mock_execution.error = None
        
        with patch.object(sandbox, 'start') as mock_start:
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.return_value = mock_execution
                
                result = await sandbox.execute("print('Hello, World!')", language="python")
        
        mock_start.assert_called_once()
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert "Hello, World!" in result.stdout

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_execute_python_code_with_error(self):
        """Test Python code execution with error."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        
        mock_execution = Mock()
        mock_execution.results = []
        mock_error = Mock()
        mock_error.traceback = "Traceback: error"
        mock_execution.error = mock_error
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = mock_execution
            
            result = await sandbox.execute("invalid code", language="python")
        
        assert result.status == SandboxStatus.FAILED
        assert result.exit_code == 1
        assert "Traceback: error" in result.stderr

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_execute_bash_command(self):
        """Test bash command execution."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        mock_command_result = Mock()
        mock_command_result.exit_code = 0
        mock_command_result.stdout = "command output"
        mock_command_result.stderr = ""
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = mock_command_result
            
            result = await sandbox.execute("echo hello", language="bash")
        
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "command output"

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_execute_bash_command_with_env_and_workdir(self):
        """Test bash command with environment and working directory."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        mock_command_result = Mock()
        mock_command_result.exit_code = 0
        mock_command_result.stdout = "output"
        mock_command_result.stderr = ""
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = mock_command_result
            
            # Test that shlex.quote is used for security
            env = {"TEST_VAR": "test value with spaces"}
            working_dir = "/path with spaces"
            
            result = await sandbox.execute(
                "echo $TEST_VAR", 
                language="bash",
                env=env,
                working_dir=working_dir
            )
        
        # Verify the command was executed
        assert result.status == SandboxStatus.COMPLETED

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_execute_timeout(self):
        """Test execution timeout handling."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = Exception("timeout occurred")
            
            result = await sandbox.execute("sleep 100", language="bash")
        
        assert result.status == SandboxStatus.FAILED

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_write_file(self):
        """Test writing file to sandbox."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = None
            
            success = await sandbox.write_file("/test.txt", "content")
        
        assert success is True

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_write_file_error(self):
        """Test writing file with error."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = Exception("Write failed")
            
            success = await sandbox.write_file("/test.txt", "content")
        
        assert success is False

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_read_file(self):
        """Test reading file from sandbox."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.return_value = "file content"
            
            content = await sandbox.read_file("/test.txt")
        
        assert content == "file content"

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_read_file_error(self):
        """Test reading file with error."""
        sandbox = E2BSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = Exception("Read failed")
            
            content = await sandbox.read_file("/test.txt")
        
        assert content is None

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_list_files(self):
        """Test listing files in sandbox."""
        sandbox = E2BSandbox()
        
        mock_result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            stdout="/file1.txt\n/file2.py\n",
            success=True
        )
        
        with patch.object(sandbox, 'run_command', return_value=mock_result):
            files = await sandbox.list_files("/")
        
        assert files == ["/file1.txt", "/file2.py"]

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_list_files_error(self):
        """Test listing files with error."""
        sandbox = E2BSandbox()
        
        with patch.object(sandbox, 'run_command', side_effect=Exception("List failed")):
            files = await sandbox.list_files("/")
        
        assert files == []

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = E2BSandbox()
        
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch.object(sandbox, 'is_available', True):
                status = sandbox.get_status()
        
        assert status["available"] is True
        assert status["type"] == "e2b"
        assert status["running"] is False
        assert status["api_key_set"] is True

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_cleanup(self):
        """Test sandbox cleanup."""
        sandbox = E2BSandbox()
        
        # Should not raise
        await sandbox.cleanup()

    @pytest.mark.skip(reason="E2B mock tests pending C13 realignment")
    async def test_reset(self):
        """Test sandbox reset."""
        sandbox = E2BSandbox()
        
        with patch.object(sandbox, 'stop') as mock_stop:
            with patch.object(sandbox, 'start') as mock_start:
                await sandbox.reset()
        
        mock_stop.assert_called_once()
        mock_start.assert_called_once()
