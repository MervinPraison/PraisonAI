"""Live integration tests for praisonai-sandbox backends (requires API keys)."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.network


@pytest.mark.asyncio
async def test_subprocess_live_execute():
    """Subprocess sandbox always works without external deps."""
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
async def test_sandbox_manager_subprocess_live():
    """End-to-end via agents SandboxManager bridge."""
    from praisonaiagents.sandbox import SandboxConfig, SandboxManager

    manager = SandboxManager(SandboxConfig.subprocess())
    result = await manager.run_code("print('manager-live-ok')")
    assert "manager-live-ok" in (result.stdout or "")


@pytest.mark.asyncio
async def test_backward_compat_shim_live():
    """praisonai.sandbox shim resolves to praisonai_sandbox at runtime."""
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
