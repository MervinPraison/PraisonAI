"""Tests for the MCP runner's Windows event-loop selection (issue #5598).

On Windows the stdio transport must spawn a child process (e.g. ``npx``) and
talk to it over pipes. A background thread gets a ``SelectorEventLoop`` by
default there, which cannot spawn subprocesses and fails with an opaque
``fileno`` error during ``MCP.__init__``. ``MCPToolRunner.run`` must instead
drive a ``ProactorEventLoop`` on Windows so subprocess stdio works.

These tests exercise the loop-selection branch directly, without a real MCP
server or a Windows host, by stubbing ``_run_async`` and ``platform.system``.
"""

import asyncio

import pytest

from praisonaiagents.mcp.mcp import MCPToolRunner


class _FakeRunner:
    """Bind ``MCPToolRunner.run`` to a bare object so no thread is started."""

    def __init__(self):
        self.ran = False

    async def _run_async(self):
        self.ran = True


def test_run_uses_proactor_loop_on_windows(monkeypatch):
    """On Windows the runner must create and drive a ProactorEventLoop so the
    stdio subprocess transport works (otherwise: RuntimeError: fileno)."""
    created = {}
    real_proactor = asyncio.SelectorEventLoop  # usable stand-in on POSIX CI

    class _SpyLoop(real_proactor):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created["loop"] = self

    monkeypatch.setattr("praisonaiagents.mcp.mcp.platform.system", lambda: "Windows")
    monkeypatch.setattr(asyncio, "ProactorEventLoop", _SpyLoop, raising=False)

    def _boom(_coro):
        raise AssertionError("asyncio.run must not be used on Windows")

    monkeypatch.setattr(asyncio, "run", _boom)

    fake = _FakeRunner()
    MCPToolRunner.run(fake)

    assert fake.ran is True
    assert "loop" in created
    assert created["loop"].is_closed()


def test_run_uses_asyncio_run_off_windows(monkeypatch):
    """Non-Windows platforms keep the standard asyncio.run path unchanged."""
    monkeypatch.setattr("praisonaiagents.mcp.mcp.platform.system", lambda: "Linux")

    calls = {"run": 0}
    real_run = asyncio.run

    def _tracked_run(coro):
        calls["run"] += 1
        return real_run(coro)

    monkeypatch.setattr(asyncio, "run", _tracked_run)

    def _no_proactor(*a, **k):
        raise AssertionError("ProactorEventLoop must not be used off Windows")

    monkeypatch.setattr(asyncio, "ProactorEventLoop", _no_proactor, raising=False)

    fake = _FakeRunner()
    MCPToolRunner.run(fake)

    assert fake.ran is True
    assert calls["run"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
