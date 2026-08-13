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
        ContextCompactionPolicy,
        ExecutionConfig,
        MemoryConfig,
        PreCompactionMemoryFlushConfig,
    )
    monkeypatch.setenv("PRAISONAI_MEMORY_DIR", str(tmp_path))
    agent = Agent(
        name="flush-real-smoke",
        instructions="Be concise.",
        memory=MemoryConfig(backend="file", user_id="flush-real-smoke"),
        execution=ExecutionConfig(
            context_compaction=ContextCompactionPolicy(
                trigger_at=0.11,
                target_utilization=0.10,
                strategy="truncate",
                preserve_last_n_turns=1,
            ),
            max_context_tokens=64,
            pre_compaction_memory_flush=PreCompactionMemoryFlushConfig(
                timeout_seconds=30,
                min_turns_to_flush=1,
            ),
        ),
    )
    agent.chat_history = [
        {"role": "user", "content": "My project codename is NEBULA-7."},
        {"role": "assistant", "content": "Filler context. " * 5000},
    ]

    output = agent.start("Reply only with: done")
    hits = agent._memory_instance.search_long_term("NEBULA-7", limit=5)

    print(output)
    assert hits
