"""Regression tests for MCPToolRunner concurrent call routing."""

import queue
import threading
import time
from unittest.mock import Mock, patch

import pytest


class TestMCPToolRunnerConcurrency:
    def test_concurrent_calls_receive_matching_results(self):
        from praisonaiagents.mcp.mcp import MCPToolRunner

        with patch.object(MCPToolRunner, "start", lambda self: None):
            runner = MCPToolRunner(server_params=Mock(), timeout=5)
        runner.initialized.set()

        results = {}
        barrier = threading.Barrier(2)

        def slow_worker():
            while True:
                item = runner.queue.get()
                if item is None:
                    break
                response_queue, _kind, tool_name, _arguments = item
                if tool_name == "slow_tool":
                    time.sleep(0.05)
                    response_queue.put((True, "slow-result"))
                else:
                    response_queue.put((True, "fast-result"))

        worker = threading.Thread(target=slow_worker, daemon=True)
        worker.start()

        def call_tool(name):
            barrier.wait()
            results[name] = runner.call_tool(name, {})

        threads = [
            threading.Thread(target=call_tool, args=("slow_tool",)),
            threading.Thread(target=call_tool, args=("fast_tool",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        runner.queue.put(None)
        worker.join(timeout=2)

        assert results["slow_tool"] == "slow-result"
        assert results["fast_tool"] == "fast-result"

    def test_call_tool_times_out_when_worker_stalls(self):
        from praisonaiagents.mcp.mcp import MCPToolRunner

        with patch.object(MCPToolRunner, "start", lambda self: None):
            runner = MCPToolRunner(server_params=Mock(), timeout=1)
        runner.initialized.set()

        result = runner.call_tool("stalled_tool", {})
        assert "timed out" in result.lower()

    def test_init_error_is_not_returned_to_unrelated_callers(self):
        from praisonaiagents.mcp.mcp import MCPToolRunner

        with patch.object(MCPToolRunner, "start", lambda self: None):
            runner = MCPToolRunner(server_params=Mock(), timeout=5)
        runner.initialized.set()
        runner._init_error = "MCP initialization error: boom"

        result = runner.call_tool("any_tool", {})
        assert result == "Error: MCP initialization error: boom"
