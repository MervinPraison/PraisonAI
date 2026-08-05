"""Unit tests for Novita Sandbox (novita-sandbox backend)."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from praisonai_sandbox.novita import NovitaSandbox
from praisonaiagents.sandbox import SandboxStatus


def _novita_sdk_module():
    mod = MagicMock()
    mod.core = MagicMock()
    mod.core.AsyncSandbox = MagicMock()
    return mod


class TestNovitaSandbox:
    def test_init_defaults(self):
        sandbox = NovitaSandbox()
        assert sandbox.sandbox_type == "novita"
        assert not sandbox._is_running

    def test_is_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            sandbox = NovitaSandbox()
            assert sandbox.is_available is False

    @patch.dict(os.environ, {"NOVITA_API_KEY": "test-key"})
    def test_is_available_with_key_and_sdk(self):
        sandbox = NovitaSandbox()
        with patch.dict(sys.modules, {"novita_sandbox": _novita_sdk_module()}):
            assert sandbox.is_available is True

    @patch.dict(os.environ, {"NOVITA_API_KEY": "test-key"})
    @patch("importlib.import_module", side_effect=ImportError())
    def test_is_available_without_sdk(self, mock_import):
        sandbox = NovitaSandbox()
        assert sandbox.is_available is False

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"NOVITA_API_KEY": "test-key"})
    async def test_start_success(self):
        sandbox = NovitaSandbox()
        mock_sandbox = AsyncMock()
        mock_async_sandbox_cls = AsyncMock()
        mock_async_sandbox_cls.create = AsyncMock(return_value=mock_sandbox)

        with patch("praisonai_sandbox.novita.NovitaSandbox.is_available", True):
            with patch.dict(
                sys.modules,
                {"novita_sandbox.core": MagicMock(AsyncSandbox=mock_async_sandbox_cls)},
            ):
                await sandbox.start()

        assert sandbox._is_running
        assert sandbox._sandbox is mock_sandbox
        mock_async_sandbox_cls.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_not_available(self):
        sandbox = NovitaSandbox()
        with pytest.raises(RuntimeError, match="Novita is not available"):
            await sandbox.start()

    @pytest.mark.asyncio
    async def test_execute_python(self):
        sandbox = NovitaSandbox()
        sandbox._is_running = True
        mock_result = Mock(stdout="novita-ok", stderr="", exit_code=0, error=None)
        mock_sandbox = AsyncMock()
        mock_sandbox.commands.run = AsyncMock(return_value=mock_result)
        sandbox._sandbox = mock_sandbox

        result = await sandbox.execute("print('novita-ok')", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert "novita-ok" in (result.stdout or "")

    @pytest.mark.asyncio
    async def test_stop_kills_sandbox(self):
        sandbox = NovitaSandbox()
        mock_sandbox = AsyncMock()
        sandbox._sandbox = mock_sandbox
        sandbox._is_running = True

        await sandbox.stop()

        mock_sandbox.kill.assert_called_once()
        assert not sandbox._is_running

    def test_get_status(self):
        with patch.dict(os.environ, {"NOVITA_API_KEY": "secret"}):
            sandbox = NovitaSandbox()
            status = sandbox.get_status()
        assert status["type"] == "novita"
        assert status["api_key_set"] is True
        assert status["running"] is False
