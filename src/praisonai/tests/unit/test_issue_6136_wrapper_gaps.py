"""Regression tests for #6136: Replay bridge, tools lazy cache, sync provider offload."""
import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest


def test_tools_lazy_attr_is_stable_and_uses_lazy_cache():
    import praisonai.tools as tools

    first = tools.multiedit
    second = tools.multiedit
    assert callable(first) and first is second  # not shadowed by the submodule
    with pytest.raises(AttributeError):
        tools.does_not_exist


def test_replay_runner_records_async_target_through_real_bridge(tmp_path, monkeypatch):
    import json

    from praisonai.replay import live
    from praisonaiagents.trace.context_events import get_context_emitter

    monkeypatch.setenv("PRAISONAI_TRACES_DIR", str(tmp_path))
    caller = threading.get_ident()
    seen = {}

    async def target(text):
        seen["thread"] = threading.get_ident()
        get_context_emitter().agent_start("bridge-agent", {"input": text})

    live._runner(target)("hi", "run-6136")

    assert seen["thread"] != caller  # ran on the bridge loop, not a fresh asyncio.run
    events = [json.loads(line) for line in (tmp_path / "run-6136.jsonl").read_text().splitlines() if line.strip()]
    agent_events = [e for e in events if e.get("agent_name") == "bridge-agent"]
    assert agent_events, events  # contextvars-bound emitter reached the bridge thread
    assert all(e.get("session_id") == "run-6136" for e in agent_events)


def test_sync_registered_provider_is_offloaded_off_the_loop():
    from praisonai.auto import AutoGenerator

    loop_thread = {}

    class Provider:
        def generate_structured(self, response_model, messages, **kwargs):
            return threading.get_ident()

    gen = AutoGenerator.__new__(AutoGenerator)
    gen.config_list = [{"model": "myprov/m"}]

    async def go():
        loop_thread["id"] = threading.get_ident()
        return await gen._structured_via_registered_provider(MagicMock(), [], "myprov/m")

    with patch("praisonai.llm.has_llm_provider", return_value=True), \
         patch("praisonai.llm.create_llm_provider", return_value=Provider()):
        worker = asyncio.run(go())
    assert worker != loop_thread["id"]


def test_async_registered_provider_is_awaited():
    from praisonai.auto import AutoGenerator

    class Provider:
        async def generate_structured(self, response_model, messages, **kwargs):
            return "ok"

    gen = AutoGenerator.__new__(AutoGenerator)
    gen.config_list = [{"model": "myprov/m"}]
    with patch("praisonai.llm.has_llm_provider", return_value=True), \
         patch("praisonai.llm.create_llm_provider", return_value=Provider()):
        assert asyncio.run(gen._structured_via_registered_provider(MagicMock(), [], "myprov/m")) == "ok"
