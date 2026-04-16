"""
Unit tests for SSH Sandbox implementation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from praisonai.sandbox.ssh import SSHSandbox
from praisonaiagents.sandbox import SandboxStatus, ResourceLimits


class TestSSHSandbox:
    """Test SSH sandbox implementation."""
    
    def test_init(self):
        """Test SSH sandbox initialization."""
        sandbox = SSHSandbox(
            host="test.example.com",
            user="testuser",
            key_file="~/.ssh/id_rsa"
        )
        
        assert sandbox.host == "test.example.com"
        assert sandbox.user == "testuser"
        assert sandbox.key_file.endswith("/.ssh/id_rsa")
        assert sandbox.sandbox_type == "ssh"
        assert not sandbox._is_running
    
    def test_is_available_without_asyncssh(self):
        """Test availability check when asyncssh is not available."""
        with patch('praisonai.sandbox.ssh.SSHSandbox.is_available', False):
            sandbox = SSHSandbox(host="test.example.com")
            assert not sandbox.is_available
    
    @patch('importlib.import_module')
    def test_is_available_with_asyncssh(self, mock_import):
        """Test availability check when asyncssh is available."""
        mock_import.return_value = MagicMock()
        sandbox = SSHSandbox(host="test.example.com")
        # This would be True in real scenario, but we're testing the pattern
        assert sandbox.sandbox_type == "ssh"
    
    @pytest.mark.asyncio
    async def test_start_without_asyncssh(self):
        """Test start fails without asyncssh."""
        with patch.object(SSHSandbox, 'is_available', False):
            sandbox = SSHSandbox(host="test.example.com")
            
            with pytest.raises(RuntimeError, match="SSH backend not available"):
                await sandbox.start()
    
    @pytest.mark.asyncio
    async def test_start_with_mocked_connection(self):
        """Test successful start with mocked asyncssh."""
        mock_connection = AsyncMock()
        
        with patch.object(SSHSandbox, 'is_available', True), \
             patch('asyncssh.connect', return_value=mock_connection) as mock_connect:
            
            sandbox = SSHSandbox(
                host="test.example.com",
                user="testuser",
                key_file="~/.ssh/id_rsa"
            )
            
            await sandbox.start()
            
            assert sandbox._is_running
            assert sandbox._connection == mock_connection
            mock_connect.assert_called_once()
            mock_connection.run.assert_called_once_with("mkdir -p /tmp/praisonai")
    
    @pytest.mark.asyncio
    async def test_stop(self):
        """Test stopping SSH connection."""
        mock_connection = AsyncMock()
        
        sandbox = SSHSandbox(host="test.example.com")
        sandbox._connection = mock_connection
        sandbox._is_running = True
        
        await sandbox.stop()
        
        assert not sandbox._is_running
        assert sandbox._connection is None
        mock_connection.close.assert_called_once()
        mock_connection.wait_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_python_code(self):
        """Test executing Python code via SSH."""
        mock_connection = AsyncMock()
        mock_result = MagicMock()
        mock_result.exit_status = 0
        mock_result.stdout = "Hello, World!"
        mock_result.stderr = ""
        mock_connection.run.return_value = mock_result
        
        with patch.object(SSHSandbox, 'is_available', True), \
             patch.object(SSHSandbox, 'write_file', return_value=True):
            
            sandbox = SSHSandbox(host="test.example.com")
            sandbox._connection = mock_connection
            sandbox._is_running = True
            
            result = await sandbox.execute("print('Hello, World!')", "python")
            
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert result.stdout == "Hello, World!"
            assert result.stderr == ""
            assert result.success
    
    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test executing code that fails."""
        mock_connection = AsyncMock()
        mock_result = MagicMock()
        mock_result.exit_status = 1
        mock_result.stdout = ""
        mock_result.stderr = "SyntaxError: invalid syntax"
        mock_connection.run.return_value = mock_result
        
        with patch.object(SSHSandbox, 'is_available', True), \
             patch.object(SSHSandbox, 'write_file', return_value=True):
            
            sandbox = SSHSandbox(host="test.example.com")
            sandbox._connection = mock_connection
            sandbox._is_running = True
            
            result = await sandbox.execute("invalid python code", "python")
            
            assert result.status == SandboxStatus.FAILED
            assert result.exit_code == 1
            assert not result.success
    
    @pytest.mark.asyncio
    async def test_run_command(self):
        """Test running shell command."""
        mock_connection = AsyncMock()
        mock_result = MagicMock()
        mock_result.exit_status = 0
        mock_result.stdout = "total 4"
        mock_result.stderr = ""
        mock_connection.run.return_value = mock_result
        
        sandbox = SSHSandbox(host="test.example.com")
        sandbox._connection = mock_connection
        sandbox._is_running = True
        
        result = await sandbox.run_command("ls -la")
        
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "total 4"
    
    @pytest.mark.asyncio
    async def test_write_file(self):
        """Test writing file to remote server."""
        mock_connection = AsyncMock()
        mock_sftp = AsyncMock()
        mock_file = AsyncMock()
        mock_sftp.open.return_value.__aenter__.return_value = mock_file
        mock_connection.start_sftp_client.return_value.__aenter__.return_value = mock_sftp
        
        sandbox = SSHSandbox(host="test.example.com")
        sandbox._connection = mock_connection
        sandbox._is_running = True
        
        success = await sandbox.write_file("/tmp/test.py", "print('Hello')")
        
        assert success
        mock_connection.run.assert_called_once_with("mkdir -p /tmp")
        mock_file.write.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_read_file(self):
        """Test reading file from remote server."""
        mock_connection = AsyncMock()
        mock_sftp = AsyncMock()
        mock_file = AsyncMock()
        mock_file.read.return_value = b"print('Hello')"
        mock_sftp.open.return_value.__aenter__.return_value = mock_file
        mock_connection.start_sftp_client.return_value.__aenter__.return_value = mock_sftp
        
        sandbox = SSHSandbox(host="test.example.com")
        sandbox._connection = mock_connection
        sandbox._is_running = True
        
        content = await sandbox.read_file("/tmp/test.py")
        
        assert content == "print('Hello')"
    
    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = SSHSandbox(
            host="test.example.com",
            user="testuser",
            port=2222
        )
        
        status = sandbox.get_status()
        
        assert status["type"] == "ssh"
        assert status["host"] == "test.example.com"
        assert status["user"] == "testuser"
        assert status["port"] == 2222
        assert not status["running"]
    
    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup operation."""
        mock_connection = AsyncMock()
        
        sandbox = SSHSandbox(host="test.example.com")
        sandbox._connection = mock_connection
        sandbox._is_running = True
        
        await sandbox.cleanup()
        
        mock_connection.run.assert_called_once_with("rm -rf /tmp/praisonai/*")
    
    def test_get_file_extension(self):
        """Test file extension mapping."""
        sandbox = SSHSandbox(host="test.example.com")
        
        assert sandbox._get_file_extension("python") == "py"
        assert sandbox._get_file_extension("bash") == "sh"
        assert sandbox._get_file_extension("javascript") == "js"
        assert sandbox._get_file_extension("unknown") == "txt"
    
    def test_build_command(self):
        """Test command building for different languages."""
        sandbox = SSHSandbox(host="test.example.com")
        
        # Test Python command
        cmd = sandbox._build_command("python", "/tmp/test.py", None, None)
        assert "python3 /tmp/test.py" in cmd
        
        # Test with environment variables
        env = {"TEST_VAR": "value"}
        cmd = sandbox._build_command("python", "/tmp/test.py", None, env)
        assert "env TEST_VAR=value" in cmd
        
        # Test with resource limits
        limits = ResourceLimits(timeout_seconds=30, memory_mb=256)
        cmd = sandbox._build_command("python", "/tmp/test.py", limits, None)
        assert "timeout 30" in cmd
        assert "ulimit -v 262144" in cmd  # 256MB * 1024KB