"""Context compaction must keep a result for every advertised tool call."""

from copy import deepcopy

import pytest

from praisonaiagents.context.manager import ContextManager, SessionDeduplicationCache
from praisonaiagents.context.models import ContextConfig, OptimizerStrategy


@pytest.mark.parametrize("shared_cache", [False, True])
def test_compaction_preserves_identical_tool_results(shared_cache, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    content = "No matching records were found. " * 10
    cache = SessionDeduplicationCache() if shared_cache else None
    config = ContextConfig(
        compact_threshold=0,
        strategy=OptimizerStrategy.TRUNCATE,
        keep_recent_turns=4,
    )
    if cache is not None:
        # Another agent has already put this text in the shared content cache.
        ContextManager(config=config, session_cache=cache, agent_name="writer").process(
            [{"role": "user", "content": content}]
        )
    manager = ContextManager(config=config, session_cache=cache, agent_name="reviewer")
    manager._budget.history = 512
    calls = [
        {"id": call_id, "type": "function", "function": {"name": "search", "arguments": "{}"}}
        for call_id in ("search_a", "search_b")
    ]
    messages = [
        {"role": "user", "content": "Earlier context. " * 2000},
        {"role": "assistant", "content": None, "tool_calls": calls},
        {"role": "tool", "tool_call_id": "search_b", "content": content},
        {"role": "tool", "tool_call_id": "search_a", "content": content},
        {"role": "user", "content": "Compare the two results."},
    ]
    original = deepcopy(messages)

    result = manager.process(messages)

    assert result["optimized"] is True
    assert result["messages"] == original[1:]
    assert messages == original
