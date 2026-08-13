"""Opt-in real-provider smoke for memory prefetch.

Run with RUN_REAL_KEY_TESTS=1 and a configured provider key.
"""

import os

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1",
    reason="requires an explicitly enabled real provider",
)
def test_real_agent_uses_prefetched_memory(tmp_path, monkeypatch):
    from praisonaiagents import Agent, MemoryConfig

    monkeypatch.setenv("PRAISONAI_MEMORY_DIR", str(tmp_path))
    config = MemoryConfig(
        backend="file",
        user_id="prefetch-real-smoke",
        prefetch=True,
        prefetch_limit=3,
    )
    writer = Agent(name="writer", instructions="Store user facts.", memory=config)
    writer.store_memory(
        "The user's project codename is NEBULA-7.",
        memory_type="long_term",
    )

    reader = Agent(
        name="reader",
        instructions="Answer only from recalled memories.",
        memory=config,
    )
    result = reader.start("What is my project codename?")

    print(result)
    assert "NEBULA-7" in str(result)
