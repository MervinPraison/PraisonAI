"""Tests for opt-in RunJournal integration and explicit resume."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents import ExecutionConfig
from praisonaiagents.agent.durable import (
    DurableRunContext,
    begin_durable_run,
    end_durable_run,
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
        "charge_card", {"amount": 10}, tool_call_id="call-1"
    )
    assert [event.kind for event in journal.events("run-1")] == [
        KIND_MODEL_DECISION,
        KIND_TOOL_CALL,
        KIND_TOOL_RESULT,
        KIND_ITERATION,
    ]
    assert journal.last_iteration("run-1") == 0
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
