"""Tests for opt-in RunJournal integration and explicit resume."""

import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents import ExecutionConfig
from praisonaiagents.errors import ToolExecutionError
from praisonaiagents.agent.durable import (
    DurableRunContext,
    _accepts_idempotency_key,
    begin_durable_run,
)
from praisonaiagents.runtime import JournalEvent, RunJournal
from praisonaiagents.runtime.journal import (
    KIND_ITERATION,
    KIND_MODEL_DECISION,
    KIND_TOOL_CALL,
    KIND_TOOL_RESULT,
)


def test_execution_config_durable_defaults_and_round_trip(tmp_path):
    assert ExecutionConfig().durable is False

    config = ExecutionConfig(
        durable=True,
        journal_path=str(tmp_path / "journal.db"),
        resume_run_id="run-1",
    )
    restored = ExecutionConfig.from_dict(config.to_dict())

    assert restored.durable is True
    assert restored.journal_path == str(tmp_path / "journal.db")
    assert restored.resume_run_id == "run-1"


def test_default_off_never_constructs_journal():
    agent = SimpleNamespace(
        execution=ExecutionConfig(durable=False),
        name="agent",
    )
    with patch("praisonaiagents.agent.durable.RunJournal") as journal_cls:
        context, token = begin_durable_run(agent, "task")

    assert (context, token) == (None, None)
    journal_cls.assert_not_called()


def test_sync_wrapper_records_completed_tool_step():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)
    tool = MagicMock(return_value={"charged": True})

    result = context.wrap_sync(tool)(
        "charge_card", {"amount": 10}, tool_call_id="call-1"
    )

    assert result == {"charged": True}
    tool.assert_called_once_with(
        "charge_card",
        {"amount": 10},
        tool_call_id="call-1",
        idempotency_key="run-1:0:charge_card",
    )
    assert [event.kind for event in journal.events("run-1")] == [
        KIND_MODEL_DECISION,
        KIND_TOOL_CALL,
        KIND_TOOL_RESULT,
        KIND_ITERATION,
    ]
    assert journal.last_iteration("run-1") == 0
    journal.close()


def test_parallel_tool_results_count_as_one_model_iteration():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)
    execute = context.wrap_sync(MagicMock(return_value="ok"))

    execute("first", {}, tool_call_id="call-1", _durable_iteration_index=0)
    execute("second", {}, tool_call_id="call-2", _durable_iteration_index=0)

    assert context.completed_steps == 1
    assert [
        event.payload["index"]
        for event in journal.events("run-1")
        if event.kind == KIND_ITERATION
    ] == [0]
    journal.close()


def test_fatal_tool_execution_error_is_recorded_and_terminal():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)
    error = ToolExecutionError("halt", tool_name="danger", is_retryable=False)

    with pytest.raises(ToolExecutionError, match="halt"):
        context.wrap_sync(MagicMock(side_effect=error))(
            "danger", {}, tool_call_id="call-1"
        )

    kinds = [event.kind for event in journal.events("run-1")]
    assert KIND_TOOL_RESULT in kinds
    assert KIND_ITERATION in kinds
    result = next(
        event.payload["result"]
        for event in journal.events("run-1")
        if event.kind == KIND_TOOL_RESULT
    )
    assert result["terminal"] is True
    assert result["is_retryable"] is False
    assert journal.run_meta("run-1").status == "failed"
    assert journal.interrupted_runs() == []
    journal.close()


def test_retryable_tool_execution_error_remains_resumable():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)
    error = ToolExecutionError("retry later", tool_name="api", is_retryable=True)

    with pytest.raises(ToolExecutionError, match="retry later"):
        context.wrap_sync(MagicMock(side_effect=error))(
            "api", {}, tool_call_id="call-1"
        )

    kinds = [event.kind for event in journal.events("run-1")]
    assert KIND_TOOL_RESULT not in kinds
    assert journal.run_meta("run-1").status == "running"
    assert journal.interrupted_runs() == ["run-1"]
    journal.close()


def test_idempotency_signature_probe_fails_closed():
    with patch("inspect.signature", side_effect=ValueError("opaque callable")):
        assert _accepts_idempotency_key(MagicMock()) is False


@pytest.mark.asyncio
async def test_async_fatal_tool_execution_error_is_terminal():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)
    error = ToolExecutionError("halt", tool_name="danger", is_retryable=False)

    with pytest.raises(ToolExecutionError, match="halt"):
        await context.wrap_async(AsyncMock(side_effect=error))(
            "danger", {}, tool_call_id="call-1"
        )

    assert journal.run_meta("run-1").status == "failed"
    assert journal.interrupted_runs() == []
    journal.close()


def test_pending_call_reuses_stable_idempotency_key_after_resume():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    original = DurableRunContext(journal, "run-1", replaying=False)

    with pytest.raises(KeyboardInterrupt):
        original.wrap_sync(MagicMock(side_effect=KeyboardInterrupt))(
            "charge_card", {"amount": 10}, tool_call_id="old-call"
        )

    captured = {}

    def charge(_name, _arguments, *, tool_call_id=None, idempotency_key=None):
        captured["call_id"] = tool_call_id
        captured["key"] = idempotency_key
        return "charged"

    resumed = DurableRunContext(journal, "run-1", replaying=True)
    result = resumed.wrap_sync(charge)(
        "charge_card", {"amount": 10}, tool_call_id="new-call"
    )

    assert result == "charged"
    assert captured["key"] == "run-1:0:charge_card"
    assert len([
        event for event in journal.events("run-1")
        if event.kind == KIND_TOOL_CALL
    ]) == 1
    journal.close()


def test_declared_tool_receives_durable_idempotency_key():
    from praisonaiagents import Agent

    captured = {}

    def charge_card(amount: int, idempotency_key: str):
        captured["amount"] = amount
        captured["key"] = idempotency_key
        return "charged"

    agent = Agent(name="agent", instructions="test", tools=[charge_card])
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)

    result = context.wrap_sync(agent.execute_tool)(
        "charge_card", {"amount": 10}, tool_call_id="call-1"
    )

    assert result == "charged"
    assert captured == {"amount": 10, "key": "run-1:0:charge_card"}
    journal.close()


@pytest.mark.asyncio
async def test_async_declared_tool_receives_durable_idempotency_key():
    from praisonaiagents import Agent

    captured = {}

    async def send_email(to: str, idempotency_key: str):
        captured["to"] = to
        captured["key"] = idempotency_key
        return "sent"

    agent = Agent(name="agent", instructions="test", tools=[send_email])
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)

    result = await context.wrap_async(agent.execute_tool_async)(
        "send_email", {"to": "user@example.com"}, tool_call_id="call-1"
    )

    assert result == "sent"
    assert captured == {
        "to": "user@example.com",
        "key": "run-1:0:send_email",
    }
    journal.close()


def test_resumed_dispatcher_uses_only_remaining_iteration_budget():
    from praisonaiagents.agent import durable as durable_module
    from praisonaiagents.agent.chat_mixin import ChatMixin

    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    for index in (0, 1):
        journal.append(JournalEvent(
            "run-1", index, KIND_ITERATION, {"index": index}
        ))
    context = DurableRunContext(journal, "run-1", replaying=True)

    owner = ChatMixin()
    owner.execution = ExecutionConfig(
        durable=True,
        max_steps=3,
    )
    token = durable_module._active_durable_run.set(context)
    try:
        assert owner._resolve_max_steps() == 1
    finally:
        durable_module._active_durable_run.reset(token)
        journal.close()


def test_explicit_resume_restores_step_and_skips_duplicate_side_effect():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    original = DurableRunContext(journal, "run-1", replaying=False)
    side_effect = MagicMock(return_value="charged")
    original.wrap_sync(side_effect)(
        "charge_card", {"amount": 10}, tool_call_id="call-1"
    )

    resumed = DurableRunContext(journal, "run-1", replaying=True)
    messages = [{"role": "user", "content": "task"}]
    resumed.restore_messages(messages)
    result = resumed.wrap_sync(side_effect)(
        "charge_card", {"amount": 10}, tool_call_id="call-1"
    )

    assert result == "charged"
    assert side_effect.call_count == 1
    assert messages[-2]["role"] == "assistant"
    assert messages[-2]["tool_calls"][0]["id"] == "call-1"
    assert messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '"charged"',
    }
    journal.close()


@pytest.mark.asyncio
async def test_async_wrapper_records_and_replays_result():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    original = DurableRunContext(journal, "run-1", replaying=False)
    side_effect = AsyncMock(return_value={"ok": True})

    first = await original.wrap_async(side_effect)(
        "send_email", {"to": "user@example.com"}, tool_call_id="call-1"
    )
    resumed = DurableRunContext(journal, "run-1", replaying=True)
    replayed = await resumed.wrap_async(side_effect)(
        "send_email", {"to": "user@example.com"}, tool_call_id="call-1"
    )

    assert first == replayed == {"ok": True}
    side_effect.assert_awaited_once()
    journal.close()


def test_resume_requires_known_running_run_and_matching_prompt(tmp_path):
    path = str(tmp_path / "journal.db")
    agent = SimpleNamespace(
        execution=ExecutionConfig(
            durable=True,
            journal_path=path,
            resume_run_id="missing",
        ),
        name="agent",
    )
    with pytest.raises(ValueError, match="unknown durable run"):
        begin_durable_run(agent, "task")

    journal = RunJournal(path)
    journal.open_run("known", task="original task")
    journal.close()
    agent.execution.resume_run_id = "known"
    with pytest.raises(ValueError, match="does not match"):
        begin_durable_run(agent, "different task")


def test_successful_finalize_removes_run_from_interrupted_candidates():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    context = DurableRunContext(journal, "run-1", replaying=False)

    assert journal.interrupted_runs() == ["run-1"]
    context.finalize("succeeded")

    assert journal.interrupted_runs() == []
    assert journal.run_meta("run-1").status == "succeeded"
    journal.close()


def test_agent_chat_lifecycle_closes_successful_durable_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_chat_impl", return_value="done"):
        assert agent.chat("task") == "done"

    assert agent.last_durable_run_id
    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "succeeded"
    assert journal.interrupted_runs() == []
    journal.close()


def test_agent_chat_exception_leaves_run_resumable(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_chat_impl", side_effect=RuntimeError("crash")):
        with pytest.raises(RuntimeError, match="crash"):
            agent.chat("task")

    journal = RunJournal(path)
    assert journal.interrupted_runs() == [agent.last_durable_run_id]
    journal.close()


def test_agent_chat_none_result_finalizes_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_chat_impl", return_value=None):
        assert agent.chat("task") is None

    run_id = agent.last_durable_run_id
    journal = RunJournal(path)
    assert journal.run_meta(run_id).status == "failed"
    assert journal.interrupted_runs() == []
    journal.close()
    assert agent.execution.resume_run_id is None


@pytest.mark.asyncio
async def test_agent_achat_none_result_finalizes_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_achat_impl", AsyncMock(return_value=None)):
        assert await agent.achat("task") is None

    run_id = agent.last_durable_run_id
    journal = RunJournal(path)
    assert journal.run_meta(run_id).status == "failed"
    assert journal.interrupted_runs() == []
    journal.close()
    assert agent.execution.resume_run_id is None


def test_custom_llm_fatal_tool_error_reaches_durable_lifecycle(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        llm={"model": "custom/test"},
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    error = ToolExecutionError(
        "terminal tool failure", tool_name="danger", is_retryable=False
    )
    agent.llm_instance = SimpleNamespace(
        get_response=MagicMock(side_effect=error)
    )

    with pytest.raises(ToolExecutionError, match="terminal tool failure"):
        agent.chat("task")

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "failed"
    journal.close()
    assert agent.execution.resume_run_id is None


@pytest.mark.asyncio
async def test_async_custom_llm_fatal_error_reaches_durable_lifecycle(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        llm={"model": "custom/test"},
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    error = ToolExecutionError(
        "terminal tool failure", tool_name="danger", is_retryable=False
    )
    agent.llm_instance = SimpleNamespace(
        get_response_async=AsyncMock(side_effect=error)
    )

    with pytest.raises(ToolExecutionError, match="terminal tool failure"):
        await agent.achat("task")

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "failed"
    journal.close()
    assert agent.execution.resume_run_id is None


def test_agent_chat_tool_failure_finalizes_run_and_rejects_resume(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    error = ToolExecutionError(
        "terminal tool failure", tool_name="danger", is_retryable=False
    )
    with patch.object(agent, "_chat_impl", side_effect=error):
        with pytest.raises(ToolExecutionError, match="terminal tool failure"):
            agent.chat("task")

    run_id = agent.last_durable_run_id
    journal = RunJournal(path)
    assert journal.run_meta(run_id).status == "failed"
    assert journal.interrupted_runs() == []
    journal.close()

    agent.execution.resume_run_id = run_id
    with pytest.raises(ValueError, match="Cannot resume terminal durable run"):
        agent.chat("task")


def test_agent_chat_interruption_finalizes_run_as_cancelled(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_chat_impl", side_effect=InterruptedError("stop")):
        with pytest.raises(InterruptedError, match="stop"):
            agent.chat("task")

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "cancelled"
    assert journal.interrupted_runs() == []
    journal.close()


@pytest.mark.asyncio
async def test_agent_achat_task_cancellation_finalizes_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_achat_impl", side_effect=asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await agent.achat("task")

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "cancelled"
    assert journal.interrupted_runs() == []
    journal.close()


def test_stream_generator_owns_and_finalizes_durable_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(agent, "_start_stream_impl", return_value=iter(["a", "b"])):
        assert list(agent._start_stream("task")) == ["a", "b"]

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "succeeded"
    journal.close()


def test_closing_stream_generator_cancels_durable_run(tmp_path):
    from praisonaiagents import Agent

    path = str(tmp_path / "journal.db")
    agent = Agent(
        name="durable-agent",
        instructions="test",
        execution=ExecutionConfig(durable=True, journal_path=path),
    )
    with patch.object(
        agent, "_start_stream_impl", return_value=iter(["a", "b"])
    ):
        stream = agent._start_stream("task")
        assert next(stream) == "a"
        stream.close()

    journal = RunJournal(path)
    assert journal.run_meta(agent.last_durable_run_id).status == "cancelled"
    journal.close()


def test_replay_only_restores_completed_steps():
    journal = RunJournal(":memory:")
    journal.open_run("run-1", task="task")
    journal.append(JournalEvent(
        "run-1",
        0,
        KIND_MODEL_DECISION,
        {"message": {"role": "assistant", "content": "pending"}},
    ))
    context = DurableRunContext(journal, "run-1", replaying=True)
    messages = [{"role": "user", "content": "task"}]

    context.restore_messages(messages)

    assert messages == [{"role": "user", "content": "task"}]
    journal.close()
