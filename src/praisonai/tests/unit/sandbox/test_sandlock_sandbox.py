"""
Tests for SandlockSandbox implementation.
"""

import asyncio
import importlib
import os
import sys
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from praisonaiagents.sandbox import ResourceLimits, SandboxConfig, SandboxStatus


def _make_sandbox(mock_sandlock):
    """Instantiate SandlockSandbox with *mock_sandlock* injected via sys.modules."""
    # Remove any cached version so the import block inside __init__ re-runs.
    sys.modules.pop("praisonai.sandbox.sandlock", None)
    with patch.dict("sys.modules", {"sandlock": mock_sandlock}):
        from praisonai.sandbox.sandlock import SandlockSandbox
        sandbox = SandlockSandbox()
    # Keep the mock wired up after the context manager exits.
    sandbox._sandlock = mock_sandlock
    return sandbox


class TestSandlockSandbox:
    """Test SandlockSandbox functionality."""

    def test_import_without_sandlock(self):
        """Test that SandlockSandbox raises ImportError without sandlock."""
        sys.modules.pop("praisonai.sandbox.sandlock", None)
        # Ensure sandlock is absent from sys.modules so the import inside
        # __init__ actually raises ImportError.
        with patch.dict("sys.modules", {"sandlock": None}):
            # Re-import the module fresh so it picks up the patched sys.modules.
            if "praisonai.sandbox.sandlock" in sys.modules:
                del sys.modules["praisonai.sandbox.sandlock"]
            from praisonai.sandbox.sandlock import SandlockSandbox

            with pytest.raises(ImportError, match="sandlock package required"):
                SandlockSandbox()

    def test_fallback_to_subprocess_when_unavailable(self):
        """Test fallback to subprocess when sandlock is not available."""
        mock_sandlock = Mock()
        mock_sandlock.landlock_abi_version.return_value = 0  # < 1, so unavailable

        sandbox = _make_sandbox(mock_sandlock)
        assert not sandbox.is_available
        assert sandbox.sandbox_type == "sandlock"

    @pytest.mark.asyncio
    async def test_fallback_execution(self):
        """Test that execution falls back to subprocess when sandlock unavailable."""
        mock_sandlock = Mock()
        mock_sandlock.landlock_abi_version.return_value = 0  # < 1, so unavailable

        sandbox = _make_sandbox(mock_sandlock)

        mock_subprocess_instance = AsyncMock()
        mock_subprocess_instance.execute.return_value = Mock(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout="Hello, World!",
            stderr="",
        )

        with patch("praisonai.sandbox.subprocess.SubprocessSandbox") as mock_subprocess:
            mock_subprocess.return_value = mock_subprocess_instance
            result = await sandbox.execute("print('Hello, World!')")

            mock_subprocess.assert_called_once()
            mock_subprocess_instance.execute.assert_called_once()

    def test_policy_creation_with_minimal_limits(self):
        """Test policy creation with minimal resource limits."""
        mock_sandlock = Mock()
        mock_policy = Mock()
        mock_sandlock.Policy.return_value = mock_policy

        sandbox = _make_sandbox(mock_sandlock)

        limits = ResourceLimits.minimal()
        sandbox._create_policy(limits, "/tmp/workspace")

        mock_sandlock.Policy.assert_called_once()
        call_kwargs = mock_sandlock.Policy.call_args[1]

        assert "fs_readable" in call_kwargs
        assert "fs_writable" in call_kwargs
        assert "max_memory" in call_kwargs
        assert call_kwargs["max_memory"] == "128M"  # From minimal limits
        assert call_kwargs["max_processes"] == 5
        assert call_kwargs["net_allow_hosts"] == []  # Network disabled

    def test_status_reporting(self):
        """Test sandbox status reporting."""
        mock_sandlock = Mock()
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)
        status = sandbox.get_status()

        assert status["type"] == "sandlock"
        assert status["available"] is True
        assert status["landlock_supported"] is True
        assert "features" in status
        assert status["features"]["filesystem_isolation"] is True
        assert status["features"]["network_isolation"] is True
        assert status["features"]["syscall_filtering"] is True

    @pytest.mark.asyncio
    async def test_sandlock_execution_success(self):
        """Test successful code execution with sandlock."""
        mock_sandlock = Mock()
        mock_result = Mock()
        mock_result.exit_code = 0
        mock_result.stdout = "Hello, World!"
        mock_result.stderr = ""

        mock_sandlock.Policy.return_value = Mock()
        mock_sandlock.Sandbox.return_value = Mock(run=Mock(return_value=mock_result))
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_result)

            await sandbox.start()
            result = await sandbox.execute("print('Hello, World!')")

        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "Hello, World!"
        assert result.metadata["sandbox_type"] == "sandlock"
        assert result.metadata["landlock_enabled"] is True

    @pytest.mark.asyncio
    async def test_sandlock_execution_timeout(self):
        """Test timeout handling in sandlock execution."""
        mock_sandlock = Mock()
        mock_sandlock.Policy.return_value = Mock()
        mock_sandlock.Sandbox.return_value = Mock()
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)

        # Create a mock Result object indicating timeout
        mock_timeout_result = Mock()
        mock_timeout_result.success = False
        mock_timeout_result.exit_code = 124  # Common timeout exit code
        mock_timeout_result.stdout = ""
        mock_timeout_result.stderr = "Process timed out"

        # Simulate timeout by returning failed Result after enough time
        with patch("asyncio.get_running_loop") as mock_loop, \
             patch("time.time", side_effect=[0, 11, 11]):  # Started at 0, ended at 11s (> 10s timeout)
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=mock_timeout_result
            )

            await sandbox.start()
            result = await sandbox.execute("import time; time.sleep(100)", limits=ResourceLimits(timeout_seconds=10))

        assert result.status == SandboxStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_sandlock_execution_failure(self):
        """Test general execution failure handling."""
        mock_sandlock = Mock()
        mock_sandlock.Policy.return_value = Mock()
        mock_sandlock.Sandbox.return_value = Mock()
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)

        # Create a mock Result object indicating non-zero exit
        mock_failed_result = Mock()
        mock_failed_result.success = False
        mock_failed_result.exit_code = 1  # Non-zero exit code
        mock_failed_result.stdout = ""
        mock_failed_result.stderr = "Permission denied"

        # Simulate execution failure (not timeout) 
        with patch("asyncio.get_running_loop") as mock_loop, \
             patch("time.time", side_effect=[0, 2, 2]):  # Started at 0, ended at 2s (< 10s timeout)
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=mock_failed_result
            )

            await sandbox.start()
            result = await sandbox.execute("import os; os.system('rm -rf /')")

        assert result.status == SandboxStatus.FAILED
        assert "exit code 1" in result.error
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_safe_sandbox_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked by _safe_sandbox_path."""
        mock_sandlock = Mock()
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)
        await sandbox.start()

        # Attempt to escape the sandbox root via ".."
        result = sandbox._safe_sandbox_path("../../etc/passwd")
        assert result is None

        # A normal relative path should resolve inside the sandbox
        normal = sandbox._safe_sandbox_path("subdir/file.txt")
        assert normal is not None
        assert normal.startswith(sandbox._temp_dir)

        await sandbox.stop()

    @pytest.mark.asyncio
    async def test_write_file_blocks_traversal(self):
        """Test that write_file refuses paths that escape the sandbox root."""
        mock_sandlock = Mock()
        mock_sandlock.landlock_abi_version.return_value = 6  # >= 6, so available

        sandbox = _make_sandbox(mock_sandlock)
        await sandbox.start()

        success = await sandbox.write_file("../../etc/crontab", "malicious")
        assert success is False

        await sandbox.stop()

    @pytest.mark.asyncio
    async def test_real_sandlock_integration(self):
        """Integration test with real sandlock package if available.
        
        This test uses the actual sandlock package (if available) to ensure
        the integration works with the real API surface, not just mocks.
        """
        try:
            # Try to import real sandlock
            import sandlock
            
            # Only run if Landlock is actually supported on this system
            if sandlock.landlock_abi_version() < 1:
                pytest.skip("Landlock not supported on this system")
            
            # Test with real sandlock package
            from praisonai.sandbox.sandlock import SandlockSandbox
            
            sandbox = SandlockSandbox()
            assert sandbox.is_available
            
            await sandbox.start()
            
            # Execute simple code that should succeed
            result = await sandbox.execute(
                "print('Real sandlock integration test')", 
                limits=ResourceLimits(timeout_seconds=5, memory_mb=64)
            )
            
            # Should complete successfully
            assert result.status == SandboxStatus.COMPLETED
            assert result.exit_code == 0
            assert "Real sandlock integration test" in result.stdout
            
            await sandbox.stop()
            
        except ImportError:
            pytest.skip("sandlock package not available for integration test")
