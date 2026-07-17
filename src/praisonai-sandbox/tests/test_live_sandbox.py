"""Live integration tests for praisonai-sandbox backends (requires API keys)."""

from __future__ import annotations

import os
import shutil

import pytest

pytestmark = pytest.mark.network


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        from praisonai_sandbox.docker import DockerSandbox

        return DockerSandbox().is_available
    except Exception:
        return False


@pytest.mark.asyncio
async def test_subprocess_live_execute():
    from praisonai_sandbox import SubprocessSandbox

    sandbox = SubprocessSandbox()
    await sandbox.start()
    try:
        result = await sandbox.execute("print('c13-live-ok')")
        assert result.status.value in ("completed", "success")
        assert "c13-live-ok" in (result.stdout or "")
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
async def test_docker_live_execute():
    from praisonai_sandbox import DockerSandbox

    sandbox = DockerSandbox(image="python:3.11-slim")
    await sandbox.start()
    try:
        result = await sandbox.execute("print('docker-live-ok')")
        assert "docker-live-ok" in (result.stdout or "")
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
async def test_e2b_live_execute():
    from praisonai_sandbox import E2BSandbox

    sandbox = E2BSandbox()
    if not sandbox.is_available:
        pytest.skip("E2B not available (missing package or API key)")

    await sandbox.start()
    try:
        result = await sandbox.execute("print('e2b-live-ok')")
        assert "e2b-live-ok" in (result.stdout or "")
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("DAYTONA_API_KEY"), reason="DAYTONA_API_KEY not set")
async def test_daytona_live_execute():
    from praisonai_sandbox import DaytonaSandbox

    sandbox = DaytonaSandbox()
    if not sandbox.is_available:
        pytest.skip("Daytona not available (missing daytona-sdk or API key)")

    await sandbox.start()
    try:
        result = await sandbox.execute("print('daytona-live-ok')")
        assert "daytona-live-ok" in (result.stdout or "")
    finally:
        await sandbox.stop()
        await sandbox.cleanup()


@pytest.mark.asyncio
async def test_sandbox_manager_subprocess_live():
    from praisonaiagents.sandbox import SandboxConfig, SandboxManager

    manager = SandboxManager(SandboxConfig.subprocess())
    result = await manager.run_code("print('manager-live-ok')")
    assert "manager-live-ok" in (result.stdout or "")


@pytest.mark.asyncio
@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
async def test_sandbox_manager_docker_live():
    from praisonaiagents.sandbox import SandboxConfig, SandboxManager

    manager = SandboxManager(SandboxConfig.docker("python:3.11-slim"))
    result = await manager.run_code("print('manager-docker-ok')")
    assert "manager-docker-ok" in (result.stdout or "")


@pytest.mark.asyncio
async def test_backward_compat_shim_live():
    from praisonai._bootstrap import ensure_praisonai_sandbox

    ensure_praisonai_sandbox()
    from praisonai.sandbox import SubprocessSandbox as ShimCls
    from praisonai_sandbox import SubprocessSandbox as DirectCls

    assert ShimCls is DirectCls
    sandbox = ShimCls()
    await sandbox.start()
    try:
        result = await sandbox.execute("print('shim-live-ok')")
        assert "shim-live-ok" in (result.stdout or "")
    finally:
        await sandbox.stop()
        await sandbox.cleanup()
