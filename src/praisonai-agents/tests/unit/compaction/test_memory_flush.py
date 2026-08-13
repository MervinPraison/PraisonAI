"""Tests for bounded, best-effort pre-compaction memory flush."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents import (
    ExecutionConfig,
    PreCompactionMemoryFlushConfig,
)
from praisonaiagents.compaction import ContextCompactor
from praisonaiagents.compaction.memory_flush import (
    create_memory_flush_agent,
    format_messages_to_flush,
    resolve_memory_flush_config,
    run_pre_compaction_flush,
    run_pre_compaction_flush_sync,
)


def _parent(memory=object()):
    return SimpleNamespace(
        name="parent",
        llm="gpt-4o-mini",
        _memory_instance=memory,
    )


def _messages():
    return [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "My codename is NEBULA-7"},
        {"role": "assistant", "content": "I will remember it"},
        {"role": "tool", "content": "secret tool payload"},
        {"role": "user", "content": "recent question"},
        {"role": "assistant", "content": "recent answer"},
    ]


def test_config_is_default_off_and_round_trips_nested_policy():
    assert ExecutionConfig().pre_compaction_memory_flush is False
    config = ExecutionConfig(
        context_compaction=True,
        pre_compaction_memory_flush=PreCompactionMemoryFlushConfig(
            timeout_seconds=3,
            min_turns_to_flush=4,
            max_flush_tokens=200,
        ),
    )

    restored = ExecutionConfig.from_dict(config.to_dict())

    assert isinstance(
        restored.pre_compaction_memory_flush,
        PreCompactionMemoryFlushConfig,
    )
    assert restored.pre_compaction_memory_flush.timeout_seconds == 3
    assert restored.pre_compaction_memory_flush.min_turns_to_flush == 4
    assert restored.pre_compaction_memory_flush.max_flush_tokens == 200


def test_env_can_force_disable_or_enable(monkeypatch):
    monkeypatch.setenv("PRAISONAI_PRE_COMPACTION_FLUSH", "0")
    assert resolve_memory_flush_config(True).enabled is False

    monkeypatch.setenv("PRAISONAI_PRE_COMPACTION_FLUSH", "1")
    assert resolve_memory_flush_config(False).enabled is True


def test_preview_older_slice_uses_compactor_boundary():
    compactor = ContextCompactor(preserve_recent=2)

    older = compactor.preview_older_slice(_messages())

    assert [message["content"] for message in older] == [
        "My codename is NEBULA-7",
        "I will remember it",
        "secret tool payload",
    ]


def test_preview_boundary_never_splits_tool_call_pair():
    messages = [
        {"role": "user", "content": "old"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        {"role": "user", "content": "recent"},
    ]
    compactor = ContextCompactor(preserve_recent=2)

    assert compactor.preview_older_slice(messages) == [messages[0]]


def test_transcript_excludes_system_and_tool_payloads_and_is_bounded():
    transcript = format_messages_to_flush(_messages(), max_tokens=12)

    assert "system" not in transcript
    assert "secret tool payload" not in transcript
    assert "[transcript truncated]" in transcript


def test_flush_agent_has_only_memory_tools_and_disables_compaction():
    config = PreCompactionMemoryFlushConfig()
    with patch("praisonaiagents.agent.agent.Agent") as agent_cls:
        create_memory_flush_agent(_parent(), config)

    kwargs = agent_cls.call_args.kwargs
    assert {tool.__name__ for tool in kwargs["tools"]} == {
        "search_memory",
        "store_memory",
    }
    assert kwargs["memory"] is not None
    assert kwargs["execution"].context_compaction is False


def test_sync_flush_disabled_or_without_memory_does_not_create_child():
    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent"
    ) as create:
        disabled = run_pre_compaction_flush_sync(_parent(), _messages(), False)
        no_memory = run_pre_compaction_flush_sync(_parent(None), _messages(), True)

    assert disabled.reason == "disabled"
    assert no_memory.reason == "no_memory"
    create.assert_not_called()


def test_sync_flush_error_is_non_fatal():
    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=RuntimeError("provider down"),
    ):
        result = run_pre_compaction_flush_sync(
            _parent(),
            _messages(),
            PreCompactionMemoryFlushConfig(min_turns_to_flush=1),
        )

    assert result.attempted is True
    assert result.completed is False
    assert result.reason == "error"


@pytest.mark.asyncio
async def test_async_flush_awaits_child_and_completes():
    child = SimpleNamespace(astart=AsyncMock(return_value="done"))
    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        return_value=child,
    ):
        result = await run_pre_compaction_flush(
            _parent(),
            _messages(),
            PreCompactionMemoryFlushConfig(min_turns_to_flush=1),
        )

    assert result.completed is True
    child.astart.assert_awaited_once()
    prompt = child.astart.await_args.args[0]
    assert "NEBULA-7" in prompt
    assert "secret tool payload" not in prompt


@pytest.mark.asyncio
async def test_async_timeout_is_non_fatal():
    async def slow_start(_prompt):
        await asyncio.sleep(0.05)

    child = SimpleNamespace(astart=slow_start)
    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        return_value=child,
    ):
        result = await run_pre_compaction_flush(
            _parent(),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1,
                timeout_seconds=0.001,
            ),
        )

    assert result.reason == "timeout"
    assert result.completed is False


@pytest.mark.asyncio
async def test_chat_mixin_shields_unexpected_flush_failures():
    from praisonaiagents.agent.chat_mixin import ChatMixin

    owner = SimpleNamespace(
        execution=ExecutionConfig(pre_compaction_memory_flush=True),
    )
    compactor = MagicMock()
    compactor.preview_older_slice.return_value = _messages()

    with patch(
        "praisonaiagents.compaction.memory_flush.run_pre_compaction_flush",
        side_effect=RuntimeError("unexpected"),
    ):
        result = await ChatMixin._arun_pre_compaction_memory_flush(
            owner, _messages(), compactor
        )

    assert result is None


def test_sync_compaction_continues_when_flush_runner_fails():
    from praisonaiagents.agent.chat_mixin import ChatMixin

    class Owner(ChatMixin):
        pass

    owner = Owner()
    owner.name = "test"
    owner.execution = ExecutionConfig(pre_compaction_memory_flush=True)
    owner._memory_instance = object()
    owner._strict_hooks = False
    owner._hook_runner = SimpleNamespace(
        execute_sync=MagicMock(return_value=[]),
    )
    owner._persist_compaction_checkpoint = MagicMock()
    compactor = ContextCompactor(max_tokens=1, preserve_recent=1)
    policy = SimpleNamespace(strategy=SimpleNamespace(value="truncate"))

    with patch(
        "praisonaiagents.compaction.memory_flush.run_pre_compaction_flush_sync",
        side_effect=RuntimeError("unexpected"),
    ):
        _route, compacted = owner._apply_compaction(_messages(), compactor, policy)

    assert compacted
    assert len(compacted) < len(_messages())
    owner._persist_compaction_checkpoint.assert_called_once()
