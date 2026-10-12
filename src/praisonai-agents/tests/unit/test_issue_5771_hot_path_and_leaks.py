"""Regression tests for issue #5771: context hot path, bounded growth, failure semantics."""

import asyncio
import os
import queue
import threading
import time
from unittest.mock import Mock, patch

import pytest


def test_llm_compressor_optimizer_uses_llm_path_without_typeerror():
    from praisonaiagents.context.optimizer import LLMContextCompressorOptimizer

    opt = LLMContextCompressorOptimizer(llm_client=None, protect_last_n_tokens=50)
    msgs = [{"role": "system", "content": "s"}] + [
        {"role": "user" if i % 2 else "assistant", "content": "word " * 200} for i in range(20)
    ]
    with patch.object(opt, "_sync_compress", side_effect=AssertionError("fallback used")):
        out, result = opt.optimize(msgs, 500)
    assert result.optimized_tokens < result.original_tokens


def test_failed_tiktoken_load_is_negatively_cached():
    pytest.importorskip("tiktoken")
    from praisonaiagents.context import tokens

    tokens._tokenizer_cache.pop("issue-5771-model", None)
    with patch("tiktoken.encoding_for_model", side_effect=KeyError("x")), \
            patch("tiktoken.get_encoding", side_effect=OSError("offline")) as get_enc:
        for _ in range(5):
            assert tokens.estimate_tokens_accurate("hello world", "issue-5771-model") > 0
    assert get_enc.call_count == 1
    tokens._tokenizer_cache.pop("issue-5771-model", None)


def test_heuristic_matches_per_char_formula():
    from praisonaiagents.context.tokens import estimate_tokens_heuristic

    assert estimate_tokens_heuristic("") == 0
    assert estimate_tokens_heuristic("a" * 400) == 100
    assert estimate_tokens_heuristic("héllo 世界") == int(6 * 0.25 + 3 * 1.3)


def test_job_manager_evicts_old_terminal_jobs():
    from praisonaiagents.background.job_manager import BackgroundJobManager

    jm = BackgroundJobManager()
    jm._GC_INTERVAL = 0
    try:
        for _ in range(5):
            jm.start_job(lambda: "x")
        time.sleep(0.3)
        for job in jm._jobs.values():
            job.completed_at -= 7200
        jm.start_job(lambda: "y")
        assert len(jm._jobs) == 1
    finally:
        jm.shutdown()


def test_team_completion_events_are_bounded():
    from praisonaiagents import AgentTeam

    team = AgentTeam(agents=[])
    assert team._completion_events.maxlen is not None


def test_memory_reclaims_dead_thread_connections(tmp_path):
    from praisonaiagents.memory.memory import Memory

    m = Memory(config={
        "provider": "none",
        "short_db": os.path.join(tmp_path, "s.db"),
        "long_db": os.path.join(tmp_path, "l.db"),
    })
    for _ in range(10):
        t = threading.Thread(target=m._get_stm_conn)
        t.start()
        t.join()
    assert len(m._all_connections) <= 1


def test_async_bridge_timeout_does_not_leave_non_daemon_thread():
    from praisonaiagents.utils.async_bridge import run_coroutine_from_any_context

    async def blocking():
        time.sleep(1)

    async def main():
        with pytest.raises(TimeoutError):
            run_coroutine_from_any_context(blocking(), timeout=0.1)
        alive = [t for t in threading.enumerate() if t.name == "praisonai-async-bridge"]
        assert alive and all(t.daemon for t in alive)

    asyncio.run(main())


def test_mcp_timed_out_call_is_not_executed_later():
    from praisonaiagents.mcp.mcp import MCPToolRunner

    with patch.object(MCPToolRunner, "start", lambda self: None):
        runner = MCPToolRunner(server_params=Mock(), timeout=0.1)
    runner.initialized.set()

    assert runner.call_tool("send_email", {}).startswith("Error: MCP tool call timed out")
    _response_queue, _kind, name, _args, cancelled = runner.queue.get_nowait()
    assert name == "send_email" and cancelled.is_set()


def test_invoke_observer_never_raises_into_run():
    from praisonaiagents.hooks.middleware import _invoke_observer

    def bad(_):
        raise ValueError("sync boom")

    async def abad(_):
        raise ValueError("async boom")

    _invoke_observer(bad, 1)
    _invoke_observer(abad, 1)

    async def in_loop():
        _invoke_observer(abad, 1)
        await asyncio.sleep(0.01)

    asyncio.run(in_loop())


def test_handoff_failure_returns_structured_error():
    from praisonaiagents import Agent
    from praisonaiagents.agent.handoff import handoff

    worker = Agent(name="worker", llm="gpt-4o-mini")
    worker.chat = Mock(side_effect=RuntimeError("worker LLM down"))
    source = Agent(name="src", llm="gpt-4o-mini")

    result = handoff(worker).to_tool_function(source)(task="do it")
    assert isinstance(result, dict) and result["handoff_failed"] is True
    assert "worker LLM down" in result["error"]
