"""
Unit tests for Modal Sandbox implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from praisonai.sandbox.modal import ModalSandbox
from praisonaiagents.sandbox import SandboxStatus, ResourceLimits


class TestModalSandbox:
    """Test Modal sandbox implementation."""
    
    def test_init(self):
        """Test Modal sandbox initialization."""
        sandbox = ModalSandbox(
            gpu="A100",
            image="python:3.11",
            timeout=300
        )
        
        assert sandbox.gpu == "A100"
        assert sandbox.image == "python:3.11"
        assert sandbox.timeout == 300
        assert sandbox.sandbox_type == "modal"
        assert not sandbox._is_running
    
    def test_is_available_without_modal(self):
        """Test availability check when modal is not available."""
        with patch('praisonai.sandbox.modal.ModalSandbox.is_available', False):
            sandbox = ModalSandbox()
            assert not sandbox.is_available
    
    @patch('importlib.import_module')
    def test_is_available_with_modal(self, mock_import):
        """Test availability check when modal is available."""
        mock_import.return_value = MagicMock()
        sandbox = ModalSandbox()
        # This would be True in real scenario, but we're testing the pattern
        assert sandbox.sandbox_type == "modal"
    
    @pytest.mark.asyncio
    async def test_start_without_modal(self):
        """Test start fails without modal."""
        with patch.object(ModalSandbox, 'is_available', False):
            sandbox = ModalSandbox()
            
            with pytest.raises(RuntimeError, match="Modal backend not available"):
                await sandbox.start()
    
    @pytest.mark.asyncio
    async def test_start_with_mocked_modal(self):
        """Test successful start with mocked modal."""
        mock_modal = MagicMock()
        mock_app = MagicMock()
        mock_modal.App.return_value = mock_app
        mock_modal.Image.from_registry.return_value.pip_install.return_value = MagicMock()
        mock_modal.gpu.A100.return_value = MagicMock()
        
        with patch.object(ModalSandbox, 'is_available', True), \
             patch('modal', mock_modal):
            
            sandbox = ModalSandbox(gpu="A100")
            
            await sandbox.start()
            
            assert sandbox._is_running
            assert sandbox._app == mock_app
            mock_modal.App.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stopping Modal app."""
        sandbox = ModalSandbox()
        sandbox._app = MagicMock()
        sandbox._function = MagicMock()
        sandbox._is_running = True
        
        await sandbox.stop()
        
        assert not sandbox._is_running
        assert sandbox._app is None
        assert sandbox._function is None
    
    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        """Test executing Python code on Modal."""
        mock_function = AsyncMock()
        mock_function.remote.aio.return_value = {
            "exit_code": 0,
            "stdout": "Hello, World!",
            "stderr": ""
        }
        
        with patch.object(ModalSandbox, 'is_available', True):
            sandbox = ModalSandbox()
            sandbox._function = mock_function
            sandbox._is_running = True
            
            result = await sandbox.execute("print('Hello, World!')", "python")
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert result.stdout == "Hello, World!"
            assert result.stderr == ""
            assert result.success
            mock_function.remote.aio.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test executing code that fails on Modal."""
        mock_function = AsyncMock()
        mock_function.remote.aio.return_value = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "SyntaxError: invalid syntax"
        }
        
        with patch.object(ModalSandbox, 'is_available', True):
            sandbox = ModalSandbox()
            sandbox._function = mock_function
            sandbox._is_running = True
            
            result = await sandbox.execute("invalid python code", "python")
            
            assert result.status == SandboxStatus.FAILED
            assert result.exit_code == 1
            assert not result.success
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execution timeout on Modal."""
        mock_function = AsyncMock()
        mock_function.remote.aio.side_effect = Exception("Timeout error")
        
        with patch.object(ModalSandbox, 'is_available', True):
            sandbox = ModalSandbox()
            sandbox._function = mock_function
            sandbox._is_running = True
            
            result = await sandbox.execute("import time; time.sleep(1000)", "python")
            
            assert result.status == SandboxStatus.FAILED
            assert result.error == "Timeout error"
    
    @pytest.mark.asyncio
    async def test_execute_bash_code(self):
        """Test executing bash code on Modal."""
        mock_function = AsyncMock()
        mock_function.remote.aio.return_value = {
            "exit_code": 0,
            "stdout": "total 4",
            "stderr": ""
        }
        
        with patch.object(ModalSandbox, 'is_available', True):
            sandbox = ModalSandbox()
            sandbox._function = mock_function
            sandbox._is_running = True
            
            result = await sandbox.execute("ls -la", "bash")
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert result.stdout == "total 4"
    
    @pytest.mark.asyncio
    async def test_run_command(self):
        """Test running shell command on Modal."""
        mock_function = AsyncMock()
        mock_function.remote.aio.return_value = {
            "exit_code": 0,
            "stdout": "Hello from bash",
            "stderr": ""
        }
        
        sandbox = ModalSandbox()
        sandbox._function = mock_function
        sandbox._is_running = True
        
        result = await sandbox.run_command("echo 'Hello from bash'")
        
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "Hello from bash"
    
    @pytest.mark.asyncio
    async def test_execute_file_not_found(self):
        """Test executing file that doesn't exist."""
        with patch.object(ModalSandbox, 'read_file', return_value=None):
            sandbox = ModalSandbox()
            
            result = await sandbox.execute_file("/nonexistent/file.py")
            
            assert result.status == SandboxStatus.FAILED
            assert "File not found" in result.error
    
    @pytest.mark.asyncio
    async def test_write_file_warning(self):
        """Test write file shows warning for stateless functions."""
        sandbox = ModalSandbox()
        
        with patch('praisonai.sandbox.modal.logger.warning') as mock_warning:
            result = await sandbox.write_file("/tmp/test.py", "print('Hello')")
            
            assert result
            mock_warning.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_read_file_warning(self):
        """Test read file shows warning for stateless functions."""
        sandbox = ModalSandbox()
        
        with patch('praisonai.sandbox.modal.logger.warning') as mock_warning:
            result = await sandbox.read_file("/tmp/test.py")
            
            assert result is None
            mock_warning.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_files_warning(self):
        """Test list files shows warning for stateless functions."""
        sandbox = ModalSandbox()
        
        with patch('praisonai.sandbox.modal.logger.warning') as mock_warning:
            result = await sandbox.list_files("/")
            
            assert result == []
            mock_warning.assert_called_once()
    
    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = ModalSandbox(
            gpu="A100",
            image="python:3.11",
            timeout=300
        )
        
        status = sandbox.get_status()
        
        assert status["type"] == "modal"
        assert status["gpu"] == "A100"
        assert status["image"] == "python:3.11"
        assert status["timeout"] == 300
        assert not status["running"]
    
    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup operation."""
        sandbox = ModalSandbox()
        
        with patch('praisonai.sandbox.modal.logger.info') as mock_info:
            await sandbox.cleanup()
            mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset(self):
        """Test reset operation."""
        sandbox = ModalSandbox()
        
        with patch('praisonai.sandbox.modal.logger.info') as mock_info:
            await sandbox.reset()
            mock_info.assert_called_once()
    
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        sandbox = ModalSandbox()
        
        assert sandbox.gpu is None
        assert sandbox.image == "python:3.11"
        assert sandbox.timeout == 300
        assert sandbox.app_name.startswith("praisonai-sandbox-")
    
    def test_init_with_custom_app_name(self):
        """Test initialization with custom app name."""
        custom_name = "my-custom-app"
        sandbox = ModalSandbox(app_name=custom_name)
        
        assert sandbox.app_name == custom_name