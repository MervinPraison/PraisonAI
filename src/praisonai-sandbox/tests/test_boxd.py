"""Unit tests for boxd Sandbox (boxd SDK backend)."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from praisonai_sandbox.boxd import BoxdSandbox
from praisonaiagents.sandbox import ResourceLimits, SandboxConfig, SandboxStatus


def _fake_client():
    client = MagicMock()
    client.machines.create = MagicMock(return_value=SimpleNamespace(id="m-123"))
    client.machines.wait_until_ready = MagicMock()
    client.machines.exec = MagicMock(
        return_value=SimpleNamespace(stdout="boxd-ok\n", stderr="", exit_code=0)
    )
    client.machines.delete = MagicMock()
    client.machines.files.upload = MagicMock(return_value=2)
    client.machines.files.download = MagicMock(return_value=b"hi")
    client.machines.files.list_dir = MagicMock()
    return client


def _running(**kwargs):
    sandbox = BoxdSandbox(api_key="test-key", **kwargs)
    sandbox._client = _fake_client()
    sandbox.machine_id = "m-123"
    sandbox._is_running = True
    return sandbox


class TestBoxdSandbox:
    def test_init_defaults(self):
        sandbox = BoxdSandbox()
        assert sandbox.sandbox_type == "boxd"
        assert not sandbox._is_running

    def test_is_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            sandbox = BoxdSandbox()
            assert sandbox.is_available is False

    @patch.dict(os.environ, {"BOXD_API_KEY": "test-key"})
    def test_is_available_with_key_and_sdk(self):
        sandbox = BoxdSandbox()
        with patch.dict(sys.modules, {"boxd": MagicMock()}):
            assert sandbox.is_available is True

    @patch.dict(os.environ, {"BOXD_API_KEY": "test-key"})
    @patch("importlib.import_module", side_effect=ImportError())
    def test_is_available_without_sdk(self, mock_import):
        sandbox = BoxdSandbox()
        assert sandbox.is_available is False

    @patch.dict(os.environ, {"BOXD_ORG": "acme", "BOXD_REGION": "fra"})
    def test_org_and_region_from_env(self):
        sandbox = BoxdSandbox(api_key="test-key")
        assert sandbox.org == "acme"
        assert sandbox.region == "fra"

    def test_uses_the_sync_client_so_calls_work_from_any_event_loop(self):
        sdk = MagicMock()
        with patch.dict(sys.modules, {"boxd": sdk}):
            client = BoxdSandbox(api_key="test-key", region="fra")._get_client()
        sdk.Boxd.assert_called_once_with(api_key="test-key", region="fra")
        assert client is sdk.Boxd.return_value

    def test_run_command_from_separate_event_loops(self):
        import asyncio

        sandbox = _running()
        first = asyncio.run(sandbox.run_command("echo 1"))
        second = asyncio.run(sandbox.run_command("echo 2"))
        assert first.status == second.status == SandboxStatus.COMPLETED
        assert sandbox._client.machines.exec.call_count == 2

    @pytest.mark.asyncio
    async def test_start_not_available(self):
        with patch.dict(os.environ, {}, clear=True):
            sandbox = BoxdSandbox()
            with pytest.raises(RuntimeError, match="boxd is not available"):
                await sandbox.start()

    @pytest.mark.asyncio
    async def test_start_creates_isolated_machine_and_waits(self):
        sandbox = BoxdSandbox(api_key="test-key", org="acme", vcpu=4, memory="16G")
        client = _fake_client()
        with patch("praisonai_sandbox.boxd.BoxdSandbox.is_available", True):
            with patch.object(sandbox, "_get_client", return_value=client):
                await sandbox.start()

        assert sandbox._is_running
        assert sandbox.machine_id == "m-123"
        name = client.machines.create.call_args.args[0]
        assert name.startswith("praisonai-")
        kwargs = client.machines.create.call_args.kwargs
        assert kwargs["isolated"] is True
        assert kwargs["org"] == "acme"
        assert kwargs["vcpu"] == 4 and kwargs["memory"] == "16G"
        client.machines.wait_until_ready.assert_called_once_with("m-123")

    @pytest.mark.asyncio
    async def test_start_from_snapshot(self):
        sandbox = BoxdSandbox(api_key="test-key", from_snapshot="py-tools")
        client = _fake_client()
        with patch("praisonai_sandbox.boxd.BoxdSandbox.is_available", True):
            with patch.object(sandbox, "_get_client", return_value=client):
                await sandbox.start()
        kwargs = client.machines.create.call_args.kwargs
        assert kwargs["from_snapshot"] == "py-tools"
        assert kwargs["isolated"] is True
        assert "vcpu" not in kwargs and "org" not in kwargs

    @pytest.mark.asyncio
    async def test_start_deletes_machine_when_not_ready(self):
        sandbox = BoxdSandbox(api_key="test-key")
        client = _fake_client()
        client.machines.wait_until_ready.side_effect = TimeoutError("not ready")
        with patch("praisonai_sandbox.boxd.BoxdSandbox.is_available", True):
            with patch.object(sandbox, "_get_client", return_value=client):
                with pytest.raises(TimeoutError):
                    await sandbox.start()
        client.machines.delete.assert_called_once_with("m-123")
        assert sandbox.machine_id is None
        assert not sandbox._is_running

    @pytest.mark.asyncio
    async def test_start_deletes_machine_when_cancelled(self):
        import asyncio

        sandbox = BoxdSandbox(api_key="test-key")
        client = _fake_client()
        client.machines.wait_until_ready.side_effect = asyncio.CancelledError()
        with patch("praisonai_sandbox.boxd.BoxdSandbox.is_available", True):
            with patch.object(sandbox, "_get_client", return_value=client):
                with pytest.raises(asyncio.CancelledError):
                    await sandbox.start()
        client.machines.delete.assert_called_once_with("m-123")
        assert sandbox.machine_id is None

    @pytest.mark.asyncio
    async def test_stop_deletes_a_machine_that_never_became_ready(self):
        sandbox = BoxdSandbox(api_key="test-key")
        sandbox._client = _fake_client()
        sandbox.machine_id = "m-123"
        await sandbox.stop()
        sandbox._client.machines.delete.assert_called_once_with("m-123")

    @pytest.mark.asyncio
    async def test_execute_python(self):
        sandbox = _running()
        result = await sandbox.execute("print('boxd-ok')", language="python")

        assert result.status == SandboxStatus.COMPLETED
        assert result.exit_code == 0
        assert "boxd-ok" in result.stdout
        args = sandbox._client.machines.exec.call_args
        assert args.args[0] == "m-123"
        assert args.args[1][:2] == ["bash", "-c"]
        assert args.args[1][2].startswith("python3 -c ")

    @pytest.mark.asyncio
    async def test_exec_passes_env_cwd_and_timeout(self):
        sandbox = _running(config=SandboxConfig(sandbox_type="boxd", env={"A": "1", "B": "1"}))
        await sandbox.run_command(
            "echo $A",
            env={"B": "2"},
            working_dir="/tmp",
            limits=ResourceLimits(timeout_seconds=7),
        )
        kwargs = sandbox._client.machines.exec.call_args.kwargs
        assert kwargs["env"] == {"A": "1", "B": "2"}
        assert kwargs["cwd"] == "/tmp"
        assert kwargs["timeout"] == 7

    @pytest.mark.asyncio
    async def test_run_command_list_is_quoted(self):
        sandbox = _running()
        await sandbox.run_command(["echo", "a b"])
        assert sandbox._client.machines.exec.call_args.args[1] == ["bash", "-c", "echo 'a b'"]

    @pytest.mark.asyncio
    async def test_commands_run_through_bash_so_vars_see_env(self):
        sandbox = _running()
        await sandbox.run_command("echo $FOO | tr a-z A-Z", env={"FOO": "bar"})
        args = sandbox._client.machines.exec.call_args
        assert args.args[1] == ["bash", "-c", "echo $FOO | tr a-z A-Z"]
        assert args.kwargs["env"] == {"FOO": "bar"}

    @pytest.mark.asyncio
    async def test_nonzero_exit_is_failed_with_stderr(self):
        sandbox = _running()
        sandbox._client.machines.exec.return_value = SimpleNamespace(
            stdout="", stderr="boom\n", exit_code=3
        )
        result = await sandbox.run_command("exit 3")
        assert result.status == SandboxStatus.FAILED
        assert result.exit_code == 3
        assert result.stderr == "boom\n"

    @pytest.mark.asyncio
    async def test_exec_timeout_maps_to_timeout_status(self):
        sandbox = _running()
        sandbox._client.machines.exec.side_effect = Exception("exec timed out after 2s")
        result = await sandbox.run_command("sleep 10", limits=ResourceLimits(timeout_seconds=2))
        assert result.status == SandboxStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_write_and_read_file(self):
        sandbox = _running()
        assert await sandbox.write_file("/tmp/a/b.txt", "hi") is True
        sandbox._client.machines.files.upload.assert_called_once_with("m-123", "/tmp/a/b.txt", "hi")
        assert await sandbox.read_file("/tmp/a/b.txt") == "hi"

    @pytest.mark.asyncio
    async def test_read_missing_file_returns_none(self):
        sandbox = _running()
        sandbox._client.machines.files.download.side_effect = Exception("no such file")
        assert await sandbox.read_file("/nope") is None

    @pytest.mark.asyncio
    async def test_list_files_returns_file_paths(self):
        sandbox = _running()
        sandbox._client.machines.files.list_dir.return_value = SimpleNamespace(
            entries=[
                SimpleNamespace(name="a.py", is_dir=False),
                SimpleNamespace(name="sub", is_dir=True),
            ],
            truncated=False,
        )
        assert await sandbox.list_files("/tmp/") == ["/tmp/a.py"]

    @pytest.mark.asyncio
    async def test_stop_deletes_machine_by_id(self):
        sandbox = _running()
        client = sandbox._client

        await sandbox.stop()

        client.machines.delete.assert_called_once_with("m-123")
        assert not sandbox._is_running
        assert sandbox.machine_id is None

    @pytest.mark.asyncio
    async def test_stop_survives_delete_error(self):
        sandbox = _running()
        sandbox._client.machines.delete.side_effect = Exception("gone")
        await sandbox.stop()
        assert not sandbox._is_running

    @pytest.mark.asyncio
    async def test_stop_deletes_without_worker_threads(self):
        sandbox = _running()
        client = sandbox._client
        with patch("praisonai_sandbox.boxd.asyncio.to_thread",
                   side_effect=RuntimeError("cannot schedule new futures after interpreter shutdown")):
            await sandbox.stop()
        client.machines.delete.assert_called_once_with("m-123")

    def test_get_status(self):
        sandbox = BoxdSandbox(api_key="secret", region="nyc")
        status = sandbox.get_status()
        assert status["type"] == "boxd"
        assert status["api_key_set"] is True
        assert status["running"] is False
        assert status["region"] == "nyc"

    def test_registered(self):
        from praisonai_sandbox._registry import SandboxRegistry

        assert SandboxRegistry.default().resolve("boxd") is BoxdSandbox
        from praisonai_sandbox import BoxdSandbox as Exported

        assert Exported is BoxdSandbox
        assert SandboxConfig.boxd().sandbox_type == "boxd"
