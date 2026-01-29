"""
Integration tests for Sandbox module.

These tests verify the Sandbox protocols and implementations work correctly
with real scenarios.
"""

import pytest
from unittest.mock import MagicMock

# Import from core SDK
from praisonaiagents.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxStatus,
    ResourceLimits,
)
from praisonaiagents.sandbox.protocols import SandboxProtocol


class TestSandboxConfigIntegration:
    """Integration tests for SandboxConfig."""
    
    def test_docker_sandbox_config(self):
        """Test Docker sandbox configuration."""
        config = SandboxConfig(
            sandbox_type='docker',
            image='python:3.11-slim',
        )
        assert config.sandbox_type == 'docker'
        assert config.image == 'python:3.11-slim'
        # Network is controlled via resource_limits
        assert config.resource_limits.network_enabled is False
    
    def test_subprocess_sandbox_config(self):
        """Test subprocess sandbox configuration."""
        limits = ResourceLimits(timeout_seconds=30)
        config = SandboxConfig(
            sandbox_type='subprocess',
            resource_limits=limits,
        )
        assert config.sandbox_type == 'subprocess'
        assert config.resource_limits.timeout_seconds == 30
    
    def test_config_with_resource_limits(self):
        """Test config with resource limits."""
        limits = ResourceLimits(
            memory_mb=256,
            cpu_percent=50,
            timeout_seconds=60,
            network_enabled=False,
        )
        
        config = SandboxConfig(
            sandbox_type='docker',
            resource_limits=limits,
        )
        
        assert config.resource_limits.memory_mb == 256
        assert config.resource_limits.cpu_percent == 50


class TestResourceLimitsIntegration:
    """Integration tests for ResourceLimits."""
    
    def test_minimal_limits(self):
        """Test minimal resource limits for untrusted code."""
        limits = ResourceLimits.minimal()
        
        assert limits.memory_mb == 128
        assert limits.cpu_percent == 50
        assert limits.timeout_seconds == 30
        assert limits.network_enabled is False
    
    def test_standard_limits(self):
        """Test standard resource limits."""
        limits = ResourceLimits.standard()
        
        assert limits.memory_mb == 512
        assert limits.timeout_seconds == 60
    
    def test_generous_limits(self):
        """Test generous resource limits for trusted code."""
        limits = ResourceLimits.generous()
        
        assert limits.memory_mb == 2048
        assert limits.timeout_seconds == 300
        assert limits.network_enabled is True
    
    def test_limits_serialization_roundtrip(self):
        """Test limits can be serialized and deserialized."""
        original = ResourceLimits(
            memory_mb=1024,
            cpu_percent=75,
            timeout_seconds=120,
            max_processes=20,
            network_enabled=True,
        )
        
        limits_dict = original.to_dict()
        restored = ResourceLimits.from_dict(limits_dict)
        
        assert restored.memory_mb == original.memory_mb
        assert restored.cpu_percent == original.cpu_percent
        assert restored.timeout_seconds == original.timeout_seconds
        assert restored.max_processes == original.max_processes
        assert restored.network_enabled == original.network_enabled


class TestSandboxResultIntegration:
    """Integration tests for SandboxResult."""
    
    def test_successful_result(self):
        """Test successful execution result."""
        result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout='Hello, World!\n',
            stderr='',
            duration_seconds=0.5,
        )
        
        assert result.success is True
        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert 'Hello' in result.stdout
    
    def test_failed_result(self):
        """Test failed execution result."""
        result = SandboxResult(
            status=SandboxStatus.FAILED,
            exit_code=1,
            stdout='',
            stderr='Error: Division by zero',
            error='Execution failed',
        )
        
        assert result.success is False
        assert result.status == SandboxStatus.FAILED
        assert 'Division by zero' in result.stderr
    
    def test_timeout_result(self):
        """Test timeout execution result."""
        result = SandboxResult(
            status=SandboxStatus.TIMEOUT,
            exit_code=None,
            stdout='Partial output...',
            stderr='',
            error='Execution timed out after 60 seconds',
            duration_seconds=60.0,
        )
        
        assert result.success is False
        assert result.status == SandboxStatus.TIMEOUT
        assert 'timed out' in result.error
    
    def test_killed_result(self):
        """Test killed execution result."""
        result = SandboxResult(
            status=SandboxStatus.KILLED,
            exit_code=-9,
            stdout='',
            stderr='',
            error='Process killed due to memory limit',
        )
        
        assert result.success is False
        assert result.status == SandboxStatus.KILLED
    
    def test_combined_output(self):
        """Test combined output property."""
        result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout='Standard output\n',
            stderr='Warning: deprecated function\n',
        )
        
        output = result.output
        assert 'Standard output' in output
        assert 'Warning' in output
    
    def test_result_serialization_roundtrip(self):
        """Test result can be serialized and deserialized."""
        original = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout='Output',
            stderr='',
            duration_seconds=1.5,
            metadata={'language': 'python'},
        )
        
        result_dict = original.to_dict()
        restored = SandboxResult.from_dict(result_dict)
        
        assert restored.status == original.status
        assert restored.exit_code == original.exit_code
        assert restored.stdout == original.stdout
        assert restored.duration_seconds == original.duration_seconds
    
    def test_all_status_values(self):
        """Test all sandbox status values."""
        for status in SandboxStatus:
            result = SandboxResult(status=status)
            assert result.status == status


class TestSandboxProtocolCompliance:
    """Test that implementations comply with protocols."""
    
    def test_sandbox_protocol_methods(self):
        """Verify SandboxProtocol has all required methods."""
        required_properties = ['is_available', 'sandbox_type']
        required_methods = [
            'start', 'stop', 'execute', 'execute_file', 'run_command',
            'write_file', 'read_file', 'list_files',
            'get_status', 'cleanup', 'reset'
        ]
        
        for prop in required_properties:
            assert hasattr(SandboxProtocol, prop)
        
        for method in required_methods:
            assert hasattr(SandboxProtocol, method)


class TestMockSandboxWorkflow:
    """Test a mock sandbox workflow."""
    
    def test_code_execution_workflow(self):
        """Test complete code execution workflow."""
        # Create mock sandbox
        sandbox = MagicMock()
        sandbox.sandbox_type = 'docker'
        sandbox.is_available = True
        
        executions = []
        
        async def execute(code, language='python', limits=None, **kwargs):
            executions.append({
                'code': code,
                'language': language,
                'limits': limits,
            })
            
            # Simulate execution
            if 'error' in code.lower():
                return SandboxResult(
                    status=SandboxStatus.FAILED,
                    exit_code=1,
                    stderr='Error in code',
                )
            
            return SandboxResult(
                status=SandboxStatus.COMPLETED,
                exit_code=0,
                stdout='Execution successful',
                duration_seconds=0.1,
            )
        
        sandbox.execute = execute
        
        # Test successful execution
        import asyncio
        result = asyncio.run(
            sandbox.execute('print("Hello")', language='python')
        )
        
        assert result.status == SandboxStatus.COMPLETED
        assert len(executions) == 1
        assert executions[0]['language'] == 'python'
    
    def test_file_operations_workflow(self):
        """Test file operations in sandbox."""
        sandbox = MagicMock()
        files = {}
        
        async def write_file(path, content):
            files[path] = content
            return True
        
        async def read_file(path):
            return files.get(path)
        
        async def list_files(path='/'):
            return list(files.keys())
        
        sandbox.write_file = write_file
        sandbox.read_file = read_file
        sandbox.list_files = list_files
        
        import asyncio
        
        async def run_file_ops():
            # Write file
            await sandbox.write_file('/app/script.py', 'print("test")')
            
            # Read file
            content = await sandbox.read_file('/app/script.py')
            assert content == 'print("test")'
            
            # List files
            file_list = await sandbox.list_files('/')
            assert '/app/script.py' in file_list
        
        asyncio.run(run_file_ops())


@pytest.mark.asyncio
class TestAsyncSandboxOperations:
    """Test async sandbox operations."""
    
    async def test_async_execute(self):
        """Test async code execution."""
        async def mock_execute(code: str) -> SandboxResult:
            return SandboxResult(
                status=SandboxStatus.COMPLETED,
                exit_code=0,
                stdout=f'Executed: {code}',
            )
        
        result = await mock_execute('print("Hello")')
        
        assert result.success is True
        assert 'Executed' in result.stdout
    
    async def test_async_with_timeout(self):
        """Test async execution with timeout."""
        async def mock_execute_with_timeout(code: str, timeout: int) -> SandboxResult:
            # Simulate timeout check
            if timeout < 1:
                return SandboxResult(
                    status=SandboxStatus.TIMEOUT,
                    error='Timeout too short',
                )
            return SandboxResult(
                status=SandboxStatus.COMPLETED,
                exit_code=0,
                stdout='Done',
            )
        
        result = await mock_execute_with_timeout('long_running()', timeout=60)
        assert result.success is True


class TestSandboxSecurityPolicies:
    """Test sandbox security policies."""
    
    def test_network_disabled_by_default(self):
        """Test network is disabled by default for security."""
        limits = ResourceLimits()
        assert limits.network_enabled is False
    
    def test_minimal_limits_are_restrictive(self):
        """Test minimal limits are appropriately restrictive."""
        limits = ResourceLimits.minimal()
        
        # Should have low memory
        assert limits.memory_mb <= 256
        
        # Should have short timeout
        assert limits.timeout_seconds <= 60
        
        # Should have no network
        assert limits.network_enabled is False
        
        # Should have limited processes
        assert limits.max_processes <= 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
