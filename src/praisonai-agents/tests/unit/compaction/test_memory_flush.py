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


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_config_rejects_non_finite_timeout(value):
    with pytest.raises(ValueError, match="finite and positive"):
        PreCompactionMemoryFlushConfig(timeout_seconds=value)


def test_env_ignores_non_finite_timeout(monkeypatch):
    monkeypatch.setenv("PRAISONAI_PRE_COMPACTION_FLUSH_TIMEOUT", "inf")

    assert resolve_memory_flush_config(True).timeout_seconds == 20.0


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


def test_preview_covers_token_budget_removals_not_just_recent_count():
    # A tiny target_tokens forces budget-driven strategies (SLIDING / TRUNCATE
    # second pass) to drop more than preserve_recent older messages. The preview
    # must be a superset covering those extra removals so their durable facts
    # are still offered to the flush.
    messages = [
        {"role": "user", "content": "fact one " * 50},
        {"role": "assistant", "content": "ack one " * 50},
        {"role": "user", "content": "fact two " * 50},
        {"role": "assistant", "content": "ack two " * 50},
        {"role": "user", "content": "recent"},
    ]
    compactor = ContextCompactor(
        max_tokens=10, target_tokens=5, preserve_recent=1
    )

    older = compactor.preview_older_slice(messages)

    # preserve_recent=1 alone would preview only the first 4; the token budget
    # discards every older message, so the preview must include all 4 of them.
    assert [m["content"] for m in older] == [m["content"] for m in messages[:4]]


def test_preview_checks_budget_even_when_recent_count_keeps_every_message():
    messages = [
        {"role": "user", "content": "durable fact " * 50},
        {"role": "assistant", "content": "recent"},
    ]
    compactor = ContextCompactor(
        max_tokens=10,
        target_tokens=5,
        preserve_recent=5,
    )

    assert compactor.preview_older_slice(messages) == [messages[0]]


def test_preview_matches_truncate_second_pass_tool_pair_removal():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "result " * 50},
        {"role": "user", "content": "recent"},
    ]
    compactor = ContextCompactor(
        max_tokens=10,
        target_tokens=5,
        preserve_recent=5,
    )

    assert compactor.preview_older_slice(messages) == messages[:2]


def test_sync_flush_worker_is_daemon_and_timeout_is_non_fatal():
    import threading

    started = threading.Event()

    class _SlowChild:
        def start(self, _prompt):
            started.set()
            # Outlive the timeout; a non-daemon worker would block shutdown.
            threading.Event().wait(5)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        return_value=_SlowChild(),
    ):
        result = run_pre_compaction_flush_sync(
            _parent(),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=0.05
            ),
        )

    assert result.reason == "timeout"
    assert result.completed is False
    assert started.wait(1)
    worker = next(
        (t for t in threading.enumerate() if t.name == "memory-flush"), None
    )
    assert worker is not None and worker.daemon is True


def test_sync_timeout_discards_late_memory_writes():
    class _Backend:
        def __init__(self):
            self.commits = []

        def commit_memory_batch(self, writes, *, deadline, commit_guard):
            commit_guard.commit(lambda: self.commits.extend(writes))

    backend = _Backend()
    release = __import__("threading").Event()
    finished = __import__("threading").Event()

    class _SlowChild:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            release.wait(1)
            self.memory.store_long_term("late fact")
            finished.set()

    def _child(_parent, _config, memory_override=None):
        return _SlowChild(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = run_pre_compaction_flush_sync(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=0.01
            ),
        )
        release.set()

    assert result.reason == "timeout"
    assert finished.wait(1)
    assert backend.commits == []


def test_sync_timeout_includes_staged_memory_commit():
    import threading

    committed = []
    commit_started = threading.Event()
    release = threading.Event()
    commit_finished = threading.Event()

    class _Backend:
        def commit_memory_batch(self, writes, *, deadline, commit_guard):
            commit_started.set()
            release.wait(1)
            commit_guard.commit(lambda: committed.extend(writes))
            commit_finished.set()

    backend = _Backend()

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            self.memory.store_long_term("durable fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = run_pre_compaction_flush_sync(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=0.01
            ),
        )
        release.set()

    assert commit_started.wait(1)
    assert commit_finished.wait(1)
    assert result.reason == "timeout"
    assert result.completed is False
    assert committed == []


def test_sync_timeout_does_not_wait_for_blocked_atomic_backend():
    import threading
    import time

    commit_started = threading.Event()
    release = threading.Event()
    commit_finished = threading.Event()

    class _Backend:
        def commit_memory_batch(self, writes, *, deadline, commit_guard):
            def _blocked_atomic_operation():
                commit_started.set()
                release.wait(1)
                commit_finished.set()

            commit_guard.commit(_blocked_atomic_operation)

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            self.memory.store_long_term("durable fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    result_holder = {}
    caller_finished = threading.Event()

    def _run_flush():
        try:
            result_holder["result"] = run_pre_compaction_flush_sync(
                _parent(_Backend()),
                _messages(),
                PreCompactionMemoryFlushConfig(
                    min_turns_to_flush=1, timeout_seconds=0.1
                ),
            )
        finally:
            caller_finished.set()

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        caller = threading.Thread(target=_run_flush)
        caller.start()
        try:
            assert commit_started.wait(1)
            started_at = time.monotonic()
            assert caller_finished.wait(0.25)
            elapsed = time.monotonic() - started_at
        finally:
            release.set()
            caller.join(1)

    assert not caller.is_alive()
    assert commit_finished.wait(1)
    assert result_holder["result"].reason == "timeout"
    assert elapsed < 0.25


def test_commit_guard_cancel_blocks_unstarted_mutation():
    from praisonaiagents.compaction.memory_flush import _AtomicCommitGuard

    guard = _AtomicCommitGuard()
    guard.cancel()

    mutated = []
    assert guard.commit(lambda: mutated.append(True)) is False
    assert mutated == []
    assert guard.cancelled is True


def test_commit_guard_cancel_does_not_block_authorized_mutation():
    import threading
    import time

    from praisonaiagents.compaction.memory_flush import _AtomicCommitGuard

    guard = _AtomicCommitGuard()
    in_operation = threading.Event()
    release = threading.Event()
    committed = []

    def _slow_operation():
        in_operation.set()
        release.wait(1)
        committed.append(True)

    worker = threading.Thread(target=lambda: guard.commit(_slow_operation))
    worker.start()
    assert in_operation.wait(1)

    started = time.monotonic()
    guard.cancel()
    elapsed = time.monotonic() - started

    assert elapsed < 0.25
    release.set()
    worker.join(1)
    assert committed == [True]


def test_file_memory_batch_is_atomic_across_multiple_stores(tmp_path):
    from praisonaiagents.memory.file_memory import FileMemory

    backend = FileMemory(user_id="flush-test", base_path=str(tmp_path))

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            self.memory.store_long_term("first fact")
            self.memory.store_long_term("second fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = run_pre_compaction_flush_sync(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=1
            ),
        )

    assert result.completed is True
    assert {item.content for item in backend.get_long_term()} == {
        "first fact",
        "second fact",
    }


def test_file_memory_mixed_batch_fails_before_any_write(tmp_path):
    from praisonaiagents.memory.file_memory import FileMemory

    backend = FileMemory(user_id="flush-test", base_path=str(tmp_path))

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            self.memory.store_long_term("long fact")
            self.memory.store_short_term("short fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = run_pre_compaction_flush_sync(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=1
            ),
        )

    assert result.reason == "error"
    assert backend.get_long_term() == []
    assert backend.get_short_term() == []


def test_file_memory_short_term_promotion_fails_before_any_write(tmp_path):
    from praisonaiagents.memory.file_memory import FileMemory

    backend = FileMemory(
        user_id="flush-test",
        base_path=str(tmp_path),
        config={"short_term_limit": 1, "auto_promote": True},
    )

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        def start(self, _prompt):
            self.memory.store_short_term("first fact")
            self.memory.store_short_term("second fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = run_pre_compaction_flush_sync(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=1
            ),
        )

    assert result.reason == "error"
    assert backend.get_short_term() == []
    assert backend.get_long_term() == []


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
async def test_async_flush_uses_async_memory_commit_with_shared_deadline():
    class _Backend:
        def __init__(self):
            self.commits = []

        async def acommit_memory_batch(
            self, writes, *, deadline, commit_guard
        ):
            commit_guard.commit(lambda: self.commits.extend(writes))

    backend = _Backend()

    class _Child:
        def __init__(self, memory):
            self.memory = memory

        async def astart(self, _prompt):
            self.memory.store_long_term("durable fact")

    def _child(_parent, _config, memory_override=None):
        return _Child(memory_override)

    with patch(
        "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
        side_effect=_child,
    ):
        result = await run_pre_compaction_flush(
            _parent(backend),
            _messages(),
            PreCompactionMemoryFlushConfig(
                min_turns_to_flush=1, timeout_seconds=1
            ),
    )

    assert result.completed is True
    assert [(name, args) for name, args, _ in backend.commits] == [
        ("store_long_term", ("durable fact",))
    ]


@pytest.mark.asyncio
async def test_async_timeout_is_non_fatal():
    child = SimpleNamespace(astart=AsyncMock(return_value="unused"))

    async def raise_timeout(awaitable, *, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    with (
        patch(
            "praisonaiagents.compaction.memory_flush.create_memory_flush_agent",
            return_value=child,
        ),
        patch("asyncio.wait_for", side_effect=raise_timeout),
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
