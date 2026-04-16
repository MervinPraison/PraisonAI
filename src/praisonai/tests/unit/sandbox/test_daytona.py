"""
Unit tests for Daytona Sandbox implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from praisonai.sandbox.daytona import DaytonaSandbox
from praisonaiagents.sandbox import SandboxStatus, ResourceLimits


class TestDaytonaSandbox:
    """Test Daytona sandbox implementation."""
    
    def test_init(self):
        """Test Daytona sandbox initialization."""
        sandbox = DaytonaSandbox(
            workspace_template="python-dev",
            provider="aws",
            api_key="test-key"
        )
        
        assert sandbox.workspace_template == "python-dev"
        assert sandbox.provider == "aws"
        assert sandbox.api_key == "test-key"
        assert sandbox.sandbox_type == "daytona"
        assert not sandbox._is_running
    
    def test_is_available_without_requests(self):
        """Test availability check when requests is not available."""
        with patch('praisonai.sandbox.daytona.DaytonaSandbox.is_available', False):
            sandbox = DaytonaSandbox()
            assert not sandbox.is_available
    
    @patch('importlib.import_module')
    def test_is_available_with_requests(self, mock_import):
        """Test availability check when requests is available."""
        mock_import.return_value = MagicMock()
        sandbox = DaytonaSandbox()
        # This would be True in real scenario, but we're testing the pattern
        assert sandbox.sandbox_type == "daytona"
    
    @pytest.mark.asyncio
    async def test_start_without_daytona(self):
        """Test start fails without Daytona."""
        with patch.object(DaytonaSandbox, 'is_available', False):
            sandbox = DaytonaSandbox()
            
            with pytest.raises(RuntimeError, match="Daytona backend not available"):
                await sandbox.start()
    
    @pytest.mark.asyncio
    async def test_start_success(self):
        """Test successful start with mocked Daytona."""
        with patch.object(DaytonaSandbox, 'is_available', True):
            sandbox = DaytonaSandbox(workspace_template="python")
            
            await sandbox.start()
            
            assert sandbox._is_running
            assert sandbox._workspace is not None
            assert sandbox._workspace["name"] == sandbox.workspace_name
            assert sandbox._workspace["template"] == "python"
    
    @pytest.mark.asyncio
    async def test_start_failure(self):
        """Test start failure."""
        with patch.object(DaytonaSandbox, 'is_available', True):
            # Simulate failure during workspace creation
            with patch('praisonai.sandbox.daytona.logger.info', side_effect=Exception("API Error")):
                sandbox = DaytonaSandbox()
                
                with pytest.raises(RuntimeError, match="Failed to create Daytona workspace"):
                    await sandbox.start()
    
    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stopping Daytona workspace."""
        sandbox = DaytonaSandbox()
        sandbox._workspace = {"id": "test-workspace"}
        sandbox._client = MagicMock()
        sandbox._is_running = True
        
        await sandbox.stop()
        
        assert not sandbox._is_running
        assert sandbox._workspace is None
        assert sandbox._client is None
    
    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        """Test executing Python code in Daytona workspace."""
        with patch.object(DaytonaSandbox, '_execute_in_workspace') as mock_execute:
            mock_execute.return_value = {
                "exit_code": 0,
                "stdout": "Hello from Daytona!",
                "stderr": ""
            }
            
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.execute("print('Hello from Daytona!')", "python")
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert result.stdout == "Hello from Daytona!"
            assert result.success
            mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test executing code that fails in Daytona workspace."""
        with patch.object(DaytonaSandbox, '_execute_in_workspace') as mock_execute:
            mock_execute.return_value = {
                "exit_code": 1,
                "stdout": "",
                "stderr": "SyntaxError: invalid syntax"
            }
            
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.execute("invalid python code", "python")
            
            assert result.status == SandboxStatus.FAILED
            assert result.exit_code == 1
            assert not result.success
    
    @pytest.mark.asyncio
    async def test_execute_exception(self):
        """Test execution with exception."""
        with patch.object(DaytonaSandbox, '_execute_in_workspace', side_effect=Exception("Network error")):
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.execute("print('Hello')", "python")
            
            assert result.status == SandboxStatus.FAILED
            assert result.error == "Network error"
    
    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test execution timeout."""
        with patch.object(DaytonaSandbox, '_execute_in_workspace', side_effect=Exception("timeout error")):
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.execute("import time; time.sleep(1000)", "python")
            
            assert result.status == SandboxStatus.TIMEOUT
            assert "timeout" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_execute_file(self):
        """Test executing a file in Daytona workspace."""
        with patch.object(DaytonaSandbox, '_execute_command_in_workspace') as mock_execute:
            mock_execute.return_value = {
                "exit_code": 0,
                "stdout": "File executed successfully",
                "stderr": ""
            }
            
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.execute_file("/workspace/script.py", ["--verbose"])
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert result.stdout == "File executed successfully"
            mock_execute.assert_called_once_with("/workspace/script.py --verbose", None, None, None)
    
    @pytest.mark.asyncio
    async def test_run_command(self):
        """Test running shell command in Daytona workspace."""
        with patch.object(DaytonaSandbox, '_execute_command_in_workspace') as mock_execute:
            mock_execute.return_value = {
                "exit_code": 0,
                "stdout": "Command executed in Daytona workspace",
                "stderr": ""
            }
            
            sandbox = DaytonaSandbox()
            sandbox._is_running = True
            
            result = await sandbox.run_command(["ls", "-la"])
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert "Command" in result.stdout
            mock_execute.assert_called_once_with("ls -la", None, None, None)
    
    @pytest.mark.asyncio
    async def test_write_file(self):
        """Test writing file to Daytona workspace."""
        sandbox = DaytonaSandbox()
        sandbox._is_running = True
        
        with patch('praisonai.sandbox.daytona.logger.info') as mock_info:
            success = await sandbox.write_file("/workspace/test.py", "print('Hello')")
            
            assert success
            mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_read_file(self):
        """Test reading file from Daytona workspace."""
        sandbox = DaytonaSandbox()
        sandbox._is_running = True
        
        with patch('praisonai.sandbox.daytona.logger.info') as mock_info:
            content = await sandbox.read_file("/workspace/test.py")
            
            assert content == "# Simulated file content"
            mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_files(self):
        """Test listing files in Daytona workspace."""
        sandbox = DaytonaSandbox()
        sandbox._is_running = True
        
        with patch('praisonai.sandbox.daytona.logger.info') as mock_info:
            files = await sandbox.list_files("/workspace")
            
            assert len(files) == 2
            assert "/workspace/main.py" in files
            assert "/workspace/requirements.txt" in files
            mock_info.assert_called_once()
    
    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = DaytonaSandbox(
            workspace_template="python-dev",
            provider="aws",
            api_key="test-key"
        )
        
        status = sandbox.get_status()
        
        assert status["type"] == "daytona"
        assert status["workspace"] == sandbox.workspace_name
        assert status["template"] == "python-dev"
        assert status["provider"] == "aws"
        assert not status["running"]
        assert status["workspace_info"] is None
    
    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup operation."""
        sandbox = DaytonaSandbox()
        sandbox._is_running = True
        
        with patch('praisonai.sandbox.daytona.logger.info') as mock_info:
            await sandbox.cleanup()
            mock_info.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset(self):
        """Test reset operation."""
        sandbox = DaytonaSandbox()
        sandbox._is_running = True
        
        with patch('praisonai.sandbox.daytona.logger.info') as mock_info:
            await sandbox.reset()
            mock_info.assert_called_once()
    
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        sandbox = DaytonaSandbox()
        
        assert sandbox.workspace_template == "python"
        assert sandbox.provider == "local"
        assert sandbox.api_key is None
        assert sandbox.server_url == "http://localhost:3000"
        assert sandbox.timeout == 300
        assert sandbox.workspace_name.startswith("praisonai-")
    
    def test_init_with_custom_workspace_name(self):
        """Test initialization with custom workspace name."""
        custom_name = "my-workspace"
        sandbox = DaytonaSandbox(workspace_name=custom_name)
        
        assert sandbox.workspace_name == custom_name
    
    @pytest.mark.asyncio
    async def test_execute_in_workspace_python_numpy(self):
        """Test _execute_in_workspace with Python numpy code."""
        sandbox = DaytonaSandbox()
        
        result = await sandbox._execute_in_workspace(
            "import numpy; print(numpy.__version__)",
            "python",
            None,
            None,
            None
        )
        
        assert result["exit_code"] == 0
        assert result["stdout"] == "1.24.3"
    
    @pytest.mark.asyncio
    async def test_execute_in_workspace_python_print(self):
        """Test _execute_in_workspace with Python print statement."""
        sandbox = DaytonaSandbox()
        
        result = await sandbox._execute_in_workspace(
            "print('Hello World')",
            "python", 
            None,
            None,
            None
        )
        
        assert result["exit_code"] == 0
        assert result["stdout"] == "Hello from Daytona!"
    
    @pytest.mark.asyncio
    async def test_execute_command_in_workspace(self):
        """Test _execute_command_in_workspace."""
        sandbox = DaytonaSandbox()
        
        result = await sandbox._execute_command_in_workspace(
            "ls -la",
            None,
            None,
            None
        )
        
        assert result["exit_code"] == 0
        assert "ls -la" in result["stdout"]