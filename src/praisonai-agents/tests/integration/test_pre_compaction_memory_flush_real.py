"""Opt-in real-provider test for pre-compaction memory extraction."""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1",
    reason="requires an explicitly enabled real provider",
)
def test_real_agent_flushes_old_fact_before_compaction(tmp_path, monkeypatch):
    from praisonaiagents import (
        Agent,
        ExecutionConfig,
        MemoryConfig,
        PreCompactionMemoryFlushConfig,
    )
    from praisonaiagents.compaction import ContextCompactor

    monkeypatch.setenv("PRAISONAI_MEMORY_DIR", str(tmp_path))
    agent = Agent(
        name="flush-real-smoke",
        instructions="Be concise.",
        memory=MemoryConfig(backend="file", user_id="flush-real-smoke"),
        execution=ExecutionConfig(
            context_compaction=True,
            pre_compaction_memory_flush=PreCompactionMemoryFlushConfig(
                timeout_seconds=30,
                min_turns_to_flush=1,
            ),
        ),
    )
    messages = [
        {"role": "user", "content": "My project codename is NEBULA-7."},
        {"role": "assistant", "content": "Understood."},
        {"role": "user", "content": "A recent turn."},
    ]

    agent._run_pre_compaction_memory_flush(
        messages, ContextCompactor(preserve_recent=1)
    )
    hits = agent._memory_instance.search_long_term("NEBULA-7", limit=5)

    print(hits)
    assert hits
