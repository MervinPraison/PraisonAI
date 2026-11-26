"""MCP progress notifications flow through a real stdio server to agent streams."""

import os
import sys
import threading
from pathlib import Path

import pytest


def _runner():
    from mcp import StdioServerParameters
    from praisonaiagents.mcp.mcp import MCPToolRunner

    server = Path(__file__).parents[1] / "fixtures" / "mcp_progress_server.py"
    runner = MCPToolRunner(
        StdioServerParameters(command=sys.executable, args=[str(server)]),
        timeout=20,
    )
    assert runner.initialized.wait(timeout=20)
    assert not runner._init_error, runner._init_error
    return runner


def test_mcp_stdio_progress_reaches_stream_before_tool_result():
    pytest.importorskip("mcp")
    from praisonaiagents.streaming.events import (
        StreamEventType,
        mcp_progress_callback,
        tool_progress_channel,
    )

    runner = _runner()
    events = []
    delivered = threading.Event()
    finished = threading.Event()
    result = []

    def receive(event):
        events.append(event)
        delivered.set()

    def run_long_task(progress_sink):
        result.append(
            runner.call_tool(
                "long_task", {"task": "index", "hold": True},
                progress_sink=progress_sink,
            )
        )
        finished.set()

    try:
        with tool_progress_channel(receive):
            callback = mcp_progress_callback("long_task")
        worker = threading.Thread(target=run_long_task, args=(callback,))
        worker.start()
        assert delivered.wait(timeout=10)
        assert not finished.is_set()
        assert runner.call_tool("release_task", {}) == "Released."
        worker.join(timeout=10)
        assert finished.is_set()
        assert result == ["Completed index."]
        progress = [
            event for event in events if event.type == StreamEventType.TOOL_PROGRESS
        ]
        assert [event.content for event in progress] == ["Started", "Almost done"]
        assert [event.metadata["progress"] for event in progress] == [0.5, 1.0]
        assert all(event.metadata["source"] == "mcp" for event in progress)
    finally:
        runner.stop()


@pytest.mark.live
def test_agent_start_stream_includes_real_mcp_progress(monkeypatch, tmp_path):
    model = os.environ.get("PRAISONAI_TEST_MODEL")
    if not model:
        pytest.skip("Set PRAISONAI_TEST_MODEL to select the local inference model")
    pytest.importorskip("mcp")
    from praisonaiagents import Agent
    from praisonaiagents.streaming.events import StreamEventType, mcp_progress_callback

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    runner = _runner()

    def long_task(task: str) -> str:
        """Run a task and report progress while it runs."""
        result = runner.call_tool(
            "long_task",
            {"task": task, "hold": False},
            progress_sink=mcp_progress_callback("long_task"),
        )
        return result

    options = dict(
        instructions="When asked to run a task, call long_task and report its result.",
        llm={"model": model, "temperature": 0, "max_tokens": 128},
        tools=[long_task],
        reflection=False,
        rules=False,
        output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    events = []
    try:
        with Agent(**options) as agent:
            agent.stream_emitter.add_callback(events.append)
            output = agent.start("Call long_task with task='index'.", stream=True)
            text = "".join(output)
            print("Full Agent.start output:", text)
        assert "index" in text and "completed" in text.lower()
        assert any(event.type == StreamEventType.TOOL_PROGRESS for event in events)
    finally:
        runner.stop()
