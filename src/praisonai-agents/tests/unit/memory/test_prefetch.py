"""Tests for opt-in, turn-start long-term memory prefetch."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents import Agent, MemoryConfig
from praisonaiagents.context.tokens import estimate_tokens_heuristic


def _agent(config: MemoryConfig) -> Agent:
    if config.user_id is None:
        config.user_id = "prefetch-test-user"
    agent = Agent(
        name="prefetch-test",
        instructions="Answer from available context.",
        llm="gpt-4o-mini",
        memory=config,
    )
    # Message construction does not need a provider client; keep the unit test
    # offline by selecting the existing custom-LLM fallback branch.
    agent._using_custom_llm = True
    return agent


def test_memory_config_prefetch_defaults_and_round_trip():
    config = MemoryConfig()
    assert config.prefetch is False
    assert config.prefetch_limit == 5
    assert config.prefetch_token_budget == 512

    loaded = MemoryConfig(**MemoryConfig(
        prefetch=True,
        prefetch_limit=3,
        prefetch_token_budget=40,
    ).to_dict())
    assert loaded.prefetch is True
    assert loaded.prefetch_limit == 3
    assert loaded.prefetch_token_budget == 40


def test_prefetch_disabled_does_not_touch_backend():
    agent = _agent(MemoryConfig(prefetch=False))
    backend = MagicMock()
    agent._memory_instance = backend

    assert agent._prefetch_memory("remember this") == ""
    backend.search_long_term.assert_not_called()


def test_prefetch_injects_deduplicated_system_context_before_user_message():
    agent = _agent(MemoryConfig(
        prefetch=True,
        prefetch_limit=2,
        user_id="user-7",
        session_id="session-9",
    ))
    backend = MagicMock()
    backend.search_long_term.return_value = [
        {"memory": "Timezone: Asia/Kolkata"},
        {"text": "Preferred format: concise"},
        {"memory": "Timezone: Asia/Kolkata"},
    ]
    agent._memory_instance = backend

    recalled = agent._prefetch_memory("What timezone should I use?")
    messages, _ = agent._build_messages(
        "What timezone should I use?",
        memory_prefetch_context=recalled,
    )

    backend.search_long_term.assert_called_once_with(
        "What timezone should I use?",
        limit=2,
        user_id="user-7",
        session_id="session-9",
        metadata_filter={"session_id": "session-9"},
    )
    assert messages[0]["role"] == "system"
    assert "## Recalled memories" in messages[0]["content"]
    assert messages[0]["content"].count("Timezone: Asia/Kolkata") == 1
    assert "Preferred format: concise" in messages[0]["content"]
    assert messages[-1] == {
        "role": "user",
        "content": "What timezone should I use?",
    }


def test_prefetch_extracts_default_file_memory_search_shape():
    agent = _agent(MemoryConfig(prefetch=True))
    backend = MagicMock()
    backend.search_long_term.return_value = [
        {
            "type": "long_term",
            "item": {"content": "Timezone: Asia/Singapore"},
            "score": 0.9,
        }
    ]
    agent._memory_instance = backend

    assert agent._prefetch_memory("timezone") == "- Timezone: Asia/Singapore"


def test_prefetch_limit_and_token_budget_are_enforced_with_ellipsis():
    agent = _agent(MemoryConfig(
        prefetch=True,
        prefetch_limit=2,
        prefetch_token_budget=8,
    ))
    backend = MagicMock()
    backend.search_long_term.return_value = [
        {"text": "A long remembered preference that exceeds the budget"},
        {"text": "second memory"},
        {"text": "must not be included"},
    ]
    agent._memory_instance = backend

    recalled = agent._prefetch_memory("preference")

    assert recalled.endswith("…")
    assert "must not be included" not in recalled
    assert estimate_tokens_heuristic(recalled) <= 8


def test_prefetch_backend_failure_is_non_fatal():
    agent = _agent(MemoryConfig(prefetch=True))
    backend = MagicMock()
    backend.search_long_term.side_effect = RuntimeError("backend unavailable")
    agent._memory_instance = backend

    assert agent._prefetch_memory("question") == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prefetch_limit", None),
        ("prefetch_limit", "many"),
        ("prefetch_token_budget", None),
        ("prefetch_token_budget", "large"),
    ],
)
def test_prefetch_invalid_numeric_config_is_non_fatal(field, value):
    config = MemoryConfig(prefetch=True)
    setattr(config, field, value)
    agent = _agent(config)
    backend = MagicMock()
    agent._memory_instance = backend

    assert agent._prefetch_memory("question") == ""
    backend.search_long_term.assert_not_called()


@pytest.mark.asyncio
async def test_async_prefetch_uses_async_memory_search():
    agent = _agent(MemoryConfig(
        prefetch=True,
        prefetch_limit=1,
        user_id="user-7",
        session_id="session-9",
    ))
    agent.asearch_memory = AsyncMock(return_value=[{"text": "async memory"}])

    recalled = await agent._aprefetch_memory("async question")

    assert recalled == "- async memory"
    agent.asearch_memory.assert_awaited_once_with(
        "async question", memory_type="long_term", limit=1
    )


@pytest.mark.asyncio
async def test_async_memory_search_enforces_configured_identity_scope():
    agent = _agent(MemoryConfig(
        prefetch=True,
        user_id="user-7",
        session_id="session-9",
    ))
    backend = MagicMock()
    backend.search_long_term.return_value = []
    agent._memory_instance = backend

    await agent.asearch_memory(
        "question",
        memory_type="long_term",
        limit=2,
        user_id="other-user",
        session_id="other-session",
        metadata_filter={"session_id": "other-session", "kind": "fact"},
    )

    backend.search_long_term.assert_called_once_with(
        "question",
        2,
        user_id="user-7",
        session_id="session-9",
        metadata_filter={"session_id": "session-9", "kind": "fact"},
    )


@pytest.mark.asyncio
async def test_async_prefetch_failure_is_non_fatal():
    agent = _agent(MemoryConfig(prefetch=True))
    agent.asearch_memory = AsyncMock(side_effect=RuntimeError("offline"))

    assert await agent._aprefetch_memory("async question") == ""
