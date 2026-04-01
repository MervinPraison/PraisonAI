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
        mock_sandlock.is_available.return_value = False

        sandbox = _make_sandbox(mock_sandlock)
        assert not sandbox.is_available
        assert sandbox.sandbox_type == "sandlock"

    @pytest.mark.asyncio
    async def test_fallback_execution(self):
        """Test that execution falls back to subprocess when sandlock unavailable."""
        mock_sandlock = Mock()
        mock_sandlock.is_available.return_value = False

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
        mock_sandlock.is_available.return_value = True

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
        mock_sandlock.is_available.return_value = True

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

        class FakeTimeoutError(Exception):
            pass

        mock_sandlock.TimeoutError = FakeTimeoutError
        mock_sandlock.SecurityViolationError = Exception
        mock_sandlock.Policy.return_value = Mock()
        mock_sandlock.Sandbox.return_value = Mock()
        mock_sandlock.is_available.return_value = True

        sandbox = _make_sandbox(mock_sandlock)

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                side_effect=FakeTimeoutError()
            )

            await sandbox.start()
            result = await sandbox.execute("import time; time.sleep(100)")

        assert result.status == SandboxStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_sandlock_security_violation(self):
        """Test security violation handling."""
        mock_sandlock = Mock()

        class FakeTimeoutError(Exception):
            pass

        class FakeSecurityViolationError(Exception):
            pass

        mock_sandlock.SecurityViolationError = FakeSecurityViolationError
        mock_sandlock.TimeoutError = FakeTimeoutError
        mock_sandlock.Policy.return_value = Mock()
        mock_sandlock.Sandbox.return_value = Mock()
        mock_sandlock.is_available.return_value = True

        sandbox = _make_sandbox(mock_sandlock)

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                side_effect=FakeSecurityViolationError("Access denied")
            )

            await sandbox.start()
            result = await sandbox.execute("import os; os.system('rm -rf /')")

        assert result.status == SandboxStatus.FAILED
        assert "Security violation" in result.error
        assert "Access denied" in result.error

    @pytest.mark.asyncio
    async def test_safe_sandbox_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked by _safe_sandbox_path."""
        mock_sandlock = Mock()
        mock_sandlock.is_available.return_value = True

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
        mock_sandlock.is_available.return_value = True

        sandbox = _make_sandbox(mock_sandlock)
        await sandbox.start()

        success = await sandbox.write_file("../../etc/crontab", "malicious")
        assert success is False

        await sandbox.stop()
