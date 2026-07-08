"""
Unit tests for Capsule sandbox implementation.
"""

import pytest
from unittest.mock import Mock, patch
from praisonai.sandbox.capsule import CapsuleSandbox
from praisonaiagents.sandbox import SandboxConfig, SandboxStatus


class TestCapsuleSandbox:
    """Test Capsule sandbox implementation."""

    def test_init_default(self):
        """Test initialization with defaults."""
        sandbox = CapsuleSandbox()
        assert sandbox.sandbox_type == "capsule"
        assert not sandbox._is_running

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = SandboxConfig.capsule()
        sandbox = CapsuleSandbox(config=config)
        assert sandbox.config == config

    def test_config_capsule_factory(self):
        """Test SandboxConfig.capsule() factory."""
        config = SandboxConfig.capsule()
        assert config.sandbox_type == "capsule"
        # Strict policy for untrusted code
        assert config.security_policy.allow_network is False
        assert config.security_policy.allow_subprocess is False

    @patch.dict("sys.modules", {"capsule": Mock()})
    def test_is_available_true(self):
        """Test is_available returns True when capsule is importable."""
        sandbox = CapsuleSandbox()
        assert sandbox.is_available is True

    def test_is_available_false(self):
        """Test is_available returns False without module."""
        sandbox = CapsuleSandbox()
        with patch.dict("sys.modules", {"capsule": None}):
            assert sandbox.is_available is False

    async def test_start_not_available(self):
        """Test start when backend not available."""
        sandbox = CapsuleSandbox()
        with patch.object(CapsuleSandbox, "is_available", property(lambda self: False)):
            with pytest.raises(RuntimeError, match="Capsule backend not available"):
                await sandbox.start()

    async def test_start_already_running(self):
        """Test start when already running is a no-op."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        await sandbox.start()  # Should not raise

    async def test_execute_python_success(self):
        """Test successful Python execution."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        sandbox._sandbox.run.return_value = Mock(
            stdout="720", stderr="", exit_code=0
        )

        result = await sandbox.execute("factorial(6)", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert result.stdout == "720"
        assert result.metadata["platform"] == "capsule"

    async def test_execute_python_failure(self):
        """Test failed Python execution."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        sandbox._sandbox.run.return_value = Mock(
            stdout="", stderr="NameError", exit_code=1
        )

        result = await sandbox.execute("boom", language="python")

        assert result.status == SandboxStatus.FAILED
        assert result.exit_code == 1
        assert "NameError" in result.stderr

    async def test_execute_non_python_rejected(self):
        """Test non-Python languages are rejected."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()

        result = await sandbox.execute("echo hi", language="bash")

        assert result.status == SandboxStatus.FAILED
        assert "only supports Python" in result.error

    async def test_execute_string_result(self):
        """Test result that is a bare string is captured as stdout."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        sandbox._sandbox.run.return_value = "42"

        result = await sandbox.execute("6 * 7", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert result.stdout == "42"

    async def test_run_command_not_supported(self):
        """Test shell commands are not supported."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        result = await sandbox.run_command("ls")
        assert result.status == SandboxStatus.FAILED
        assert "does not support shell commands" in result.error

    async def test_write_read_list_not_supported(self):
        """Test file operations are not supported."""
        sandbox = CapsuleSandbox()
        assert await sandbox.write_file("/x", "y") is False
        assert await sandbox.read_file("/x") is None
        assert await sandbox.list_files("/") == []

    def test_get_status(self):
        """Test getting sandbox status."""
        sandbox = CapsuleSandbox()
        status = sandbox.get_status()
        assert status["type"] == "capsule"
        assert status["running"] is False

    async def test_stop(self):
        """Test stopping the sandbox."""
        sandbox = CapsuleSandbox()
        sandbox._is_running = True
        sandbox._sandbox = Mock()
        await sandbox.stop()
        assert not sandbox._is_running
        assert sandbox._sandbox is None

    async def test_cleanup(self):
        """Test cleanup does not raise."""
        sandbox = CapsuleSandbox()
        await sandbox.cleanup()

    async def test_reset(self):
        """Test reset stops and starts the sandbox."""
        sandbox = CapsuleSandbox()
        with patch.object(sandbox, "stop") as mock_stop:
            with patch.object(sandbox, "start") as mock_start:
                await sandbox.reset()
        mock_stop.assert_called_once()
        mock_start.assert_called_once()
