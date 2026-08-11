"""Unit tests for Daytona Sandbox (daytona-sdk backend)."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from praisonai_sandbox.daytona import DaytonaSandbox
from praisonaiagents.sandbox import SandboxStatus


def _daytona_sdk_module():
    mod = MagicMock()
    mod.Daytona = Mock()
    mod.DaytonaConfig = Mock()
    mod.CreateSandboxFromImageParams = Mock()
    mod.Resources = Mock()
    return mod


class TestDaytonaSandbox:
    def test_init_defaults(self):
        sandbox = DaytonaSandbox()
        assert sandbox.image == "python:3.12-slim"
        assert sandbox.sandbox_type == "daytona"
        assert not sandbox._is_running

    def test_is_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            sandbox = DaytonaSandbox()
            assert sandbox.is_available is False

    @patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"})
    def test_is_available_with_key_and_sdk(self):
        sandbox = DaytonaSandbox()
        with patch.dict(sys.modules, {"daytona_sdk": _daytona_sdk_module()}):
            assert sandbox.is_available is True

    @patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"})
    def test_is_available_without_sdk(self):
        sandbox = DaytonaSandbox()
        with patch.dict(sys.modules, {"daytona_sdk": None}):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **k: (_ for _ in ()).throw(ImportError())
                if name == "daytona_sdk"
                else __import__(name, *a, **k),
            ):
                assert sandbox.is_available is False

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"})
    async def test_start_success(self):
        sandbox = DaytonaSandbox(api_key="test-key")
        mock_sandbox = Mock()
        mock_client = Mock()
        mock_client.create.return_value = mock_sandbox

        with patch.dict(sys.modules, {"daytona_sdk": _daytona_sdk_module()}):
            with patch.object(sandbox, "_get_client", return_value=mock_client):
                await sandbox.start()

        assert sandbox._is_running
        assert sandbox._sandbox is mock_sandbox
        mock_client.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_not_available(self):
        sandbox = DaytonaSandbox()
        with pytest.raises(RuntimeError, match="Daytona not available"):
            await sandbox.start()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"})
    async def test_execute_python(self):
        sandbox = DaytonaSandbox(api_key="test-key")
        sandbox._is_running = True
        mock_response = Mock(result="daytona-ok", exit_code=0)
        mock_sandbox = Mock()
        mock_sandbox.process.exec.return_value = mock_response
        sandbox._sandbox = mock_sandbox

        result = await sandbox.execute("print('daytona-ok')", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert "daytona-ok" in (result.stdout or "")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"})
    async def test_stop_deletes_sandbox(self):
        sandbox = DaytonaSandbox(api_key="test-key")
        mock_sandbox = Mock()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True

        await sandbox.stop()

        mock_sandbox.delete.assert_called_once()
        assert not sandbox._is_running

    def test_get_status(self):
        sandbox = DaytonaSandbox(api_key="secret")
        status = sandbox.get_status()
        assert status["type"] == "daytona"
        assert status["api_key_set"] is True
        assert status["running"] is False
