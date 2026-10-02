"""Slow extraction and storage must not stop independent work."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Timer
from types import SimpleNamespace

import pytest

from praisonaiagents.memory.auto_memory import AutoMemory
from praisonaiagents.memory.file_memory import FileMemory


def test_slow_extraction_allows_other_interaction(tmp_path, monkeypatch):
    memory = FileMemory(user_id="extract", base_path=tmp_path)
    auto = AutoMemory(memory)
    entered, release = Event(), Event()
    original = auto.extractor.extract

    def extract(text):
        if "slow" in text:
            entered.set()
            assert release.wait(5)
        return original(text)

    monkeypatch.setattr(auto.extractor, "extract", extract)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(auto.process_interaction, "I prefer slow explanations.")
        assert entered.wait(5)
        second = pool.submit(auto.process_interaction, "I prefer fast examples.")
        try:
            assert second.result(timeout=1)
        finally:
            release.set()
        assert first.result(timeout=5)
    assert memory.get_stats()["long_term_count"] == 2


def test_identical_overlapping_extractions_store_once(tmp_path, monkeypatch):
    memory = FileMemory(user_id="overlap", base_path=tmp_path)
    auto = AutoMemory(memory)
    both_extracted = Barrier(2)
    original = auto.extractor.extract

    def extract(text):
        result = original(text)
        both_extracted.wait(timeout=5)
        return result

    monkeypatch.setattr(auto.extractor, "extract", extract)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(auto.process_interaction, "I prefer examples.") for _ in range(2)]
        results = [job.result(timeout=5) for job in jobs]
    assert sum(bool(result) for result in results) == 1
    assert FileMemory(user_id="overlap", base_path=tmp_path).get_stats()["long_term_count"] == 1


@pytest.mark.asyncio
async def test_async_after_hook_keeps_loop_live_during_storage(tmp_path, monkeypatch):
    from praisonaiagents.agent.memory_mixin import MemoryMixin
    from praisonaiagents.agent.tool_execution import ToolExecutionMixin

    class Host(MemoryMixin, ToolExecutionMixin):
        _auto_memory = True
        verbose = False

        def _drain_turn_tools(self):
            return []

        def _process_auto_learning(self):
            pass

        def _maybe_emit_nudge(self, prompt):
            return None

    host = Host()
    host._memory_instance = FileMemory(user_id="async", base_path=tmp_path)
    host._auto_memory_instance = AutoMemory(host._memory_instance)
    host._hook_runner = SimpleNamespace(registry=SimpleNamespace(has_hooks=lambda event: False))
    entered, release = Event(), Event()
    original = host._memory_instance.add_long_term

    def blocked_add(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(host._memory_instance, "add_long_term", blocked_add)
    beats = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(host._auto_memory_instance.process_interaction, "I prefer examples.")
        assert entered.wait(5)
        timer = Timer(5, release.set)  # Deadlock safeguard, not progress ordering.
        timer.start()
        def progress():
            beats.append(not release.is_set())
            release.set()
        handle = asyncio.get_running_loop().call_later(0.05, progress)
        try:
            assert await host._atrigger_after_agent_hook("I prefer diagrams.", "reply", 0) == "reply"
            await asyncio.sleep(0)
            assert beats == [True]
        finally:
            handle.cancel()
            release.set()
            timer.cancel()
            timer.join(5)
        first.result(timeout=5)
    assert host._memory_instance.get_stats()["long_term_count"] == 2


def test_pending_outage_has_backpressure_without_evicting_partial_retry(tmp_path, monkeypatch):
    from praisonaiagents.memory import auto_memory as module

    monkeypatch.setattr(module, "_MAX_PENDING_INTERACTIONS", 2, raising=False)
    memory = FileMemory(user_id="pending", base_path=tmp_path)
    auto = AutoMemory(memory)
    original = memory.add_long_term
    writes = []

    def fail(content, **kwargs):
        writes.append(content)
        if len(writes) != 1:
            raise OSError("outage")
        return original(content, **kwargs)

    monkeypatch.setattr(memory, "add_long_term", fail)
    partial = "I prefer examples. I like diagrams."
    for text in [partial, "I prefer concise answers."]:
        with pytest.raises(OSError):
            auto.process_interaction(text)
    with pytest.raises(RuntimeError, match="pending"):
        auto.process_interaction("I prefer detailed answers.")
    assert len(auto._pending_memories) == 2
    monkeypatch.setattr(memory, "add_long_term", original)
    assert auto.process_interaction("I prefer detailed answers.")
    assert auto.process_interaction(partial) == []
    contents = [item.content for item in memory.get_long_term()]
    assert contents.count("examples") == contents.count("diagrams") == 1


def test_first_overlapping_agent_calls_share_one_wrapper(tmp_path, monkeypatch):
    from praisonaiagents.agent.memory_mixin import MemoryMixin
    from praisonaiagents.memory import auto_memory as module

    class Host(MemoryMixin):
        _auto_memory = True
        verbose = False

    host = Host()
    host._memory_instance = FileMemory(user_id="first-use", base_path=tmp_path)
    entered, release, second_started = Event(), Event(), Event()
    constructed = []

    def construct(*args, **kwargs):
        constructed.append(1)
        if len(constructed) == 1:
            entered.set()
            assert release.wait(5)
        return AutoMemory(*args, **kwargs)

    monkeypatch.setattr(module, "AutoMemory", construct)
    def second_call():
        second_started.set()
        host._process_auto_memory("I prefer examples.", "reply")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(host._process_auto_memory, "I prefer examples.", "reply")
        try:
            assert entered.wait(2)
            second = pool.submit(second_call)
            assert second_started.wait(2)
            # The first constructor stays paused until both calls have started.
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert len(constructed) == 1
    assert FileMemory(user_id="first-use", base_path=tmp_path).get_stats()["long_term_count"] == 1
