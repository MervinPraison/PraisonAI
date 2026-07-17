"""
Unit tests for Daytona Sandbox implementation.

The Daytona backend is a deliberate fail-loud stub until a real Daytona client
ships: ``is_available`` is ``False`` and lifecycle/execution raise (or surface)
``NotImplementedError``. These tests lock in that contract plus the
dependency-free initialization and status behaviour.
"""

import pytest

from praisonai_sandbox.daytona import DaytonaSandbox


class TestDaytonaSandbox:
    """Test Daytona sandbox stub contract."""

    def test_init(self):
        """Test Daytona sandbox initialization with explicit args."""
        sandbox = DaytonaSandbox(
            workspace_template="python-dev",
            provider="aws",
            api_key="test-key",
        )

        assert sandbox.workspace_template == "python-dev"
        assert sandbox.provider == "aws"
        assert sandbox.api_key == "test-key"
        assert sandbox.sandbox_type == "daytona"
        assert not sandbox._is_running

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
        """Test initialization with a custom workspace name."""
        custom_name = "my-workspace"
        sandbox = DaytonaSandbox(workspace_name=custom_name)
        assert sandbox.workspace_name == custom_name

    def test_is_available_is_false(self):
        """Daytona backend advertises itself as unavailable until implemented."""
        sandbox = DaytonaSandbox()
        assert sandbox.is_available is False

    @pytest.mark.asyncio
    async def test_start_raises_not_implemented(self):
        """start() fails loud with NotImplementedError."""
        sandbox = DaytonaSandbox()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await sandbox.start()

    @pytest.mark.asyncio
    async def test_execute_fails_loud(self):
        """execute() fails loud because start() is not implemented."""
        sandbox = DaytonaSandbox()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await sandbox.execute("print('Hello')", "python")

    def test_get_status(self):
        """Test getting sandbox status without touching the workspace."""
        sandbox = DaytonaSandbox(
            workspace_template="python-dev",
            provider="aws",
            api_key="test-key",
        )

        status = sandbox.get_status()

        assert status["type"] == "daytona"
        assert status["workspace"] == sandbox.workspace_name
        assert status["template"] == "python-dev"
        assert status["provider"] == "aws"
        assert not status["running"]
        assert status["workspace_info"] is None
