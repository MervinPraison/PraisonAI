"""
Tests for SandlockSandbox implementation.
"""

import asyncio
import pytest
import sys
from unittest.mock import Mock, patch

from praisonaiagents.sandbox import ResourceLimits, SandboxConfig, SandboxStatus


class TestSandlockSandbox:
    """Test SandlockSandbox functionality."""
    
    def test_import_without_sandlock(self):
        """Test that SandlockSandbox raises ImportError without sandlock."""
        with patch.dict('sys.modules', {'sandlock': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'sandlock'")):
                from praisonai.sandbox.sandlock import SandlockSandbox
                
                with pytest.raises(ImportError, match="sandlock package required"):
                    SandlockSandbox()
    
    def test_fallback_to_subprocess_when_unavailable(self):
        """Test fallback to subprocess when sandlock is not available."""
        # Mock sandlock to be importable but not available
        mock_sandlock = Mock()
        mock_sandlock.is_available.return_value = False
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            assert not sandbox.is_available
            assert sandbox.sandbox_type == "sandlock"
    
    @pytest.mark.asyncio
    async def test_fallback_execution(self):
        """Test that execution falls back to subprocess when sandlock unavailable."""
        # Mock sandlock to be importable but not available
        mock_sandlock = Mock()
        mock_sandlock.is_available.return_value = False
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            # Mock SubprocessSandbox
            with patch('praisonai.sandbox.sandlock.SubprocessSandbox') as mock_subprocess:
                mock_subprocess_instance = Mock()
                mock_subprocess_instance.execute.return_value = Mock(
                    status=SandboxStatus.COMPLETED,
                    exit_code=0,
                    stdout="Hello, World!",
                    stderr="",
                )
                mock_subprocess.return_value = mock_subprocess_instance
                
                sandbox = SandlockSandbox()
                result = await sandbox.execute("print('Hello, World!')")
                
                # Verify SubprocessSandbox was used as fallback
                mock_subprocess.assert_called_once()
                mock_subprocess_instance.execute.assert_called_once()
    
    def test_policy_creation_with_minimal_limits(self):
        """Test policy creation with minimal resource limits."""
        # Mock sandlock
        mock_sandlock = Mock()
        mock_policy = Mock()
        mock_sandlock.Policy.return_value = mock_policy
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            sandbox._sandlock = mock_sandlock
            
            limits = ResourceLimits.minimal()
            policy = sandbox._create_policy(limits, "/tmp/workspace")
            
            # Verify Policy was called with expected parameters
            mock_sandlock.Policy.assert_called_once()
            call_kwargs = mock_sandlock.Policy.call_args[1]
            
            assert 'fs_readable' in call_kwargs
            assert 'fs_writable' in call_kwargs
            assert 'max_memory' in call_kwargs
            assert call_kwargs['max_memory'] == "128M"  # From minimal limits
            assert call_kwargs['max_processes'] == 5
            assert call_kwargs['net_allow_hosts'] == []  # Network disabled
    
    def test_status_reporting(self):
        """Test sandbox status reporting."""
        mock_sandlock = Mock()
        mock_sandlock.is_available.return_value = True
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            status = sandbox.get_status()
            
            assert status['type'] == 'sandlock'
            assert status['available'] == True
            assert status['landlock_supported'] == True
            assert 'features' in status
            assert status['features']['filesystem_isolation'] == True
            assert status['features']['network_isolation'] == True
            assert status['features']['syscall_filtering'] == True
    
    @pytest.mark.asyncio 
    async def test_sandlock_execution_success(self):
        """Test successful code execution with sandlock."""
        # Mock sandlock components
        mock_sandlock = Mock()
        mock_policy = Mock()
        mock_sandbox_instance = Mock()
        mock_result = Mock()
        mock_result.exit_code = 0
        mock_result.stdout = "Hello, World!"
        mock_result.stderr = ""
        
        mock_sandlock.Policy.return_value = mock_policy
        mock_sandlock.Sandbox.return_value = mock_sandbox_instance
        mock_sandbox_instance.run.return_value = mock_result
        mock_sandlock.is_available.return_value = True
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            sandbox._sandlock = mock_sandlock
            
            # Mock asyncio.get_event_loop().run_in_executor
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.return_value = mock_result
                
                await sandbox.start()
                result = await sandbox.execute("print('Hello, World!')")
                
                assert result.status == SandboxStatus.COMPLETED
                assert result.exit_code == 0
                assert result.stdout == "Hello, World!"
                assert result.metadata['sandbox_type'] == 'sandlock'
                assert result.metadata['landlock_enabled'] == True
    
    @pytest.mark.asyncio
    async def test_sandlock_execution_timeout(self):
        """Test timeout handling in sandlock execution."""
        mock_sandlock = Mock()
        mock_policy = Mock()
        mock_sandbox_instance = Mock()
        
        # Mock TimeoutError
        timeout_error = Exception("TimeoutError")
        timeout_error.__class__.__name__ = 'TimeoutError'
        mock_sandlock.TimeoutError = type(timeout_error)
        
        mock_sandlock.Policy.return_value = mock_policy
        mock_sandlock.Sandbox.return_value = mock_sandbox_instance
        mock_sandlock.is_available.return_value = True
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            sandbox._sandlock = mock_sandlock
            
            # Mock asyncio.get_event_loop().run_in_executor to raise TimeoutError
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = mock_sandlock.TimeoutError()
                
                await sandbox.start()
                result = await sandbox.execute("sleep 100")
                
                assert result.status == SandboxStatus.TIMEOUT
                assert "timed out" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_sandlock_security_violation(self):
        """Test security violation handling."""
        mock_sandlock = Mock()
        mock_policy = Mock()
        mock_sandbox_instance = Mock()
        
        # Mock SecurityViolationError
        security_error = Exception("Access denied")
        security_error.__class__.__name__ = 'SecurityViolationError'
        mock_sandlock.SecurityViolationError = type(security_error)
        
        mock_sandlock.Policy.return_value = mock_policy
        mock_sandlock.Sandbox.return_value = mock_sandbox_instance
        mock_sandlock.is_available.return_value = True
        
        with patch.dict('sys.modules', {'sandlock': mock_sandlock}):
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            sandbox._sandlock = mock_sandlock
            
            # Mock asyncio.get_event_loop().run_in_executor to raise SecurityViolationError
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = mock_sandlock.SecurityViolationError("Access denied")
                
                await sandbox.start()
                result = await sandbox.execute("import os; os.system('rm -rf /')")
                
                assert result.status == SandboxStatus.FAILED
                assert "Security violation" in result.error
                assert "Access denied" in result.error