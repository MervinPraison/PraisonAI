"""Regression tests for issue #6134: import side effects, launch() blocking,
and ToolsMCPServer.execute_tool inside a running event loop."""

import asyncio
import subprocess
import sys
import textwrap


def test_import_leaves_host_logging_warnings_and_env_untouched():
    code = textwrap.dedent(
        """
        import logging, os, warnings
        class H(logging.Handler):
            def emit(self, r): pass
        h = H()
        root = logging.getLogger()
        root.addHandler(h); root.setLevel(logging.INFO)
        env_before = dict(os.environ)
        warn_before = warnings.warn
        httpx_before = (logging.getLogger("httpx").level, logging.getLogger("httpx").propagate)

        import praisonaiagents  # noqa: F401

        assert root.handlers == [h], root.handlers
        assert root.level == logging.INFO
        assert warnings.warn is warn_before
        assert (logging.getLogger("httpx").level, logging.getLogger("httpx").propagate) == httpx_before
        assert dict(os.environ) == env_before, set(os.environ) ^ set(env_before)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warnings.warn("pydantic field shadows something", UserWarning)
        assert len(w) == 1
        print("OK")
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("OK")


def test_launch_does_not_read_caller_source():
    import inspect

    from praisonaiagents.agent import execution_mixin
    from praisonaiagents.agents import agents

    for mod in (execution_mixin, agents):
        src = inspect.getsource(mod)
        assert "has_more_launches" not in src
        assert "keep_alive_at_exit" in src


def test_execute_tool_async_tool_inside_running_loop():
    from praisonaiagents.mcp.mcp_server import ToolsMCPServer

    async def async_hi(x: str) -> str:
        """Say hi."""
        return f"hi {x}"

    server = ToolsMCPServer()
    server.register_tool(async_hi)
    assert server.execute_tool("async_hi", {"x": "a"}) == "hi a"

    async def main():
        return server.execute_tool("async_hi", {"x": "b"})

    assert asyncio.run(main()) == "hi b"
