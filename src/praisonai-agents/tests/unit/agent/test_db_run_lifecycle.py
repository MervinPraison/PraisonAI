"""Each public chat turn must finalize its own database run."""

import asyncio
import copy
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from praisonaiagents import Agent, MemoryConfig


class RunRecorder:
    def __init__(self):
        self.sessions = []
        self.starts = []
        self.ends = []

    def on_agent_start(self, **kwargs):
        self.sessions.append(kwargs)
        return []

    def on_user_message(self, *args, **kwargs):
        pass

    def on_agent_message(self, *args, **kwargs):
        pass

    def on_run_start(self, **kwargs):
        self.starts.append(kwargs)

    def on_run_end(self, **kwargs):
        self.ends.append(kwargs)


@pytest.fixture
def recorded_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    db = RunRecorder()
    agent = Agent(name="recorded", memory=MemoryConfig(db=db, user_id="test-user"), rules=False,
                  reflection=False, output="silent")
    return agent, db


@pytest.mark.parametrize("async_turn", [False, True])
@pytest.mark.parametrize("outcome", ["answer", "", None, ValueError("failed"), InterruptedError("cancelled")])
def test_turn_is_finalized(recorded_agent, monkeypatch, async_turn, outcome):
    agent, db = recorded_agent

    def respond(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def arespond(*args, **kwargs):
        return respond()

    monkeypatch.setattr(agent, "_chat_impl", respond)
    monkeypatch.setattr(agent, "_achat_impl", arespond)
    if isinstance(outcome, Exception):
        with pytest.raises(type(outcome), match=str(outcome)):
            asyncio.run(agent.achat("question")) if async_turn else agent.chat("question")
    else:
        result = asyncio.run(agent.achat("question")) if async_turn else agent.chat("question")
        assert result == outcome
    assert len(db.sessions) == len(db.starts) == len(db.ends) == 1
    start, end = db.starts[0], db.ends[0]
    assert start["session_id"] and start["session_id"] == end["session_id"]
    assert start["run_id"] == end["run_id"]
    assert start["input_content"] == "question"
    expected = "cancelled" if isinstance(outcome, InterruptedError) else (
        "error" if outcome is None or isinstance(outcome, Exception) else "completed")
    assert end["status"] == expected
    assert end["output_content"] == (None if isinstance(outcome, Exception) else outcome)
    assert end["metrics"]["duration_ms"] >= 0
    assert agent._current_run_id is None


def test_async_cancellation_finalizes_run(recorded_agent, monkeypatch):
    agent, db = recorded_agent

    async def scenario():
        entered = asyncio.Event()

        async def wait(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(agent, "_achat_impl", wait)
        task = asyncio.create_task(agent.achat("cancel me"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert len(db.starts) == len(db.ends) == 1
    assert db.ends[0]["status"] == "cancelled"


@pytest.mark.parametrize("block_first", [False, True])
def test_concurrent_async_turns_keep_input_output_pairs(recorded_agent, monkeypatch, block_first):
    agent, db = recorded_agent
    agent._init_db_session()
    outputs = {}

    async def scenario():
        first_entered, second_entered = asyncio.Event(), asyncio.Event()
        first_finished = asyncio.Event()

        async def respond(prompt, **kwargs):
            if prompt == "first":
                first_entered.set()
                await second_entered.wait()
                if block_first:
                    return agent._guardrail_blocked_message(ValueError("unsafe output"))
            else:
                second_entered.set()
                await first_finished.wait()
            return f"answer to {prompt}"

        monkeypatch.setattr(agent, "_achat_impl", respond)
        first = asyncio.create_task(agent.achat("first"))
        await first_entered.wait()
        second = asyncio.create_task(agent.achat("second"))
        outputs["first"] = await first
        assert outputs["first"]
        first_finished.set()
        outputs["second"] = await second
        assert outputs["second"] == "answer to second"

    asyncio.run(scenario())
    assert len(db.starts) == len(db.ends) == 2
    starts = {row["run_id"]: row["input_content"] for row in db.starts}
    assert len(starts) == 2
    for end in db.ends:
        prompt = starts[end["run_id"]]
        assert end["output_content"] == outputs[prompt]
        assert end["status"] == ("error" if prompt == "first" and block_first else "completed")


def test_before_agent_hook_receives_prompt_and_finalizes_block(recorded_agent):
    from praisonaiagents.hooks import HookEvent, HookResult

    agent, db = recorded_agent
    seen = []

    def block(data):
        seen.append(data.prompt)
        return HookResult.block("not approved")

    hook_id = agent._hook_runner.registry.register_function(HookEvent.BEFORE_AGENT, block)
    try:
        assert agent.chat("review this prompt") is None
    finally:
        agent._hook_runner.registry.unregister(hook_id)
    assert seen == ["review this prompt"]
    assert len(db.starts) == len(db.ends) == 1
    assert db.ends[0]["status"] == "error"


def test_nested_turn_restores_outer_run(recorded_agent, monkeypatch):
    agent, db = recorded_agent

    def respond(prompt, *args, **kwargs):
        outer = agent._current_run_id
        if prompt == "outer":
            assert agent.chat("inner") == "inner answer"
            assert agent._current_run_id == outer
        return f"{prompt} answer"

    monkeypatch.setattr(agent, "_chat_impl", respond)
    assert agent.chat("outer") == "outer answer"
    starts = {row["run_id"]: row["input_content"] for row in db.starts}
    assert len(starts) == len(db.ends) == 2
    for end in db.ends:
        assert end["output_content"] == f"{starts[end['run_id']]} answer"


def test_deepcopy_does_not_inherit_active_run(recorded_agent):
    # Exercise DB run state independently of optional long-term memory stores.
    agent = Agent(name="copy-recorded", memory=False, rules=False, output="silent")
    agent._db = RunRecorder()
    agent._init_db_session()
    agent._start_run("parent turn")
    original_id = agent._current_run_id
    clone = copy.deepcopy(agent)
    assert clone._current_run_id is None
    clone._start_run("clone turn")
    assert clone._current_run_id != original_id
    assert agent._current_run_id == original_id
    clone._end_run("clone answer")
    agent._end_run("parent answer")


def test_async_database_hooks_preserve_adapter_thread(recorded_agent, monkeypatch):
    agent, db = recorded_agent
    loop_thread = threading.get_ident()
    threads = []
    for name in ("on_agent_start", "on_run_start", "on_run_end"):
        original = getattr(db, name)

        def record_thread(*args, _original=original, **kwargs):
            threads.append(threading.get_ident())
            return _original(*args, **kwargs)

        monkeypatch.setattr(db, name, record_thread)

    async def respond(**kwargs):
        return "answer"

    monkeypatch.setattr(agent, "_achat_impl", respond)
    assert asyncio.run(agent.achat("question")) == "answer"
    assert len(threads) == 3 and all(t == loop_thread for t in threads)


@pytest.mark.parametrize("async_turn", [False, True])
def test_guardrail_rejection_records_blocked_output(recorded_agent, monkeypatch, async_turn):
    agent, db = recorded_agent

    def respond(*args, **kwargs):
        return agent._guardrail_blocked_message(ValueError("unsafe output"))

    async def arespond(**kwargs):
        return respond()

    monkeypatch.setattr(agent, "_chat_impl", respond)
    monkeypatch.setattr(agent, "_achat_impl", arespond)
    result = asyncio.run(agent.achat("question")) if async_turn else agent.chat("question")
    assert len(db.starts) == len(db.ends) == 1
    assert db.ends[0]["status"] == "error"
    assert db.ends[0]["output_content"] == result
    assert db.ends[0]["metrics"]["duration_ms"] >= 0
    assert "unsafe output" not in result


@pytest.mark.parametrize("async_turn", [False, True])
def test_database_failure_does_not_replace_response(recorded_agent, monkeypatch, async_turn):
    agent, db = recorded_agent

    def failed_hook(**kwargs):
        raise OSError("database unavailable")

    async def respond(**kwargs):
        return "answer"

    monkeypatch.setattr(db, "on_run_start", failed_hook)
    monkeypatch.setattr(db, "on_run_end", failed_hook)
    monkeypatch.setattr(agent, "_chat_impl", lambda *a, **kw: "answer")
    monkeypatch.setattr(agent, "_achat_impl", respond)
    result = asyncio.run(agent.achat("question")) if async_turn else agent.chat("question")
    assert result == "answer"
    assert agent._current_run_id is None


def test_async_turn_restores_database_history(recorded_agent, monkeypatch):
    from praisonaiagents.db.protocol import DbMessage

    agent, db = recorded_agent
    monkeypatch.setattr(db, "on_agent_start", lambda **kw: [
        DbMessage(role="user", content="previous question"),
        DbMessage(role="assistant", content="previous answer"),
    ])

    async def respond(**kwargs):
        assert agent.chat_history == [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        return "new answer"

    monkeypatch.setattr(agent, "_achat_impl", respond)
    assert asyncio.run(agent.achat("new question")) == "new answer"
    assert db.ends[0]["output_content"] == "new answer"


def test_async_adapter_callbacks_restore_history_and_finish_run(recorded_agent, monkeypatch):
    from praisonaiagents.db.protocol import DbMessage

    agent, db = recorded_agent
    calls = []

    def sync_hook(**kwargs):
        raise AssertionError("sync callback must not run for an async-capable adapter")

    async def begin_session(**kwargs):
        calls.append("session")
        await asyncio.sleep(0)
        return [DbMessage(role="assistant", content="saved answer")]

    async def begin_run(**kwargs):
        calls.append("start")
        db.starts.append(kwargs)
        await asyncio.sleep(0)

    async def end_run(**kwargs):
        calls.append("end")
        db.ends.append(kwargs)
        await asyncio.sleep(0)

    for name, callback in [("agent_start", begin_session), ("run_start", begin_run), ("run_end", end_run)]:
        monkeypatch.setattr(db, f"on_{name}", sync_hook)
        monkeypatch.setattr(db, f"aon_{name}", callback, raising=False)

    async def respond(**kwargs):
        assert agent.chat_history == [{"role": "assistant", "content": "saved answer"}]
        return "new answer"

    monkeypatch.setattr(agent, "_achat_impl", respond)
    assert asyncio.run(agent.achat("question")) == "new answer"
    assert calls == ["session", "start", "end"]
    assert db.starts[0]["run_id"] == db.ends[0]["run_id"]
    assert db.ends[0]["status"] == "completed"
    assert agent._current_run_id is None


def test_first_async_calls_from_different_loops_initialize_once(recorded_agent, monkeypatch):
    agent, db = recorded_agent
    entered, second_waiting, release = threading.Event(), threading.Event(), threading.Event()

    async def load(**kwargs):
        db.sessions.append(kwargs)
        entered.set()
        assert await asyncio.to_thread(release.wait, 5)
        return []

    async def respond(**kwargs):
        return "answer"

    monkeypatch.setattr(db, "aon_agent_start", load, raising=False)
    monkeypatch.setattr(agent, "_achat_impl", respond)

    def run(second=False):
        async def scenario():
            if second:
                asyncio.get_running_loop().call_soon(second_waiting.set)
            return await asyncio.wait_for(agent.achat("question"), timeout=3)

        return asyncio.run(scenario(), debug=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        try:
            assert entered.wait(3)
            second = pool.submit(run, True)
            assert second_waiting.wait(3)
        finally:
            release.set()
        assert first.result(timeout=5) == second.result(timeout=5) == "answer"
    assert len(db.sessions) == 1
    assert len(db.starts) == len(db.ends) == 2


def test_cancellation_during_final_save_finishes_record_and_cleanup(recorded_agent, monkeypatch):
    agent, db = recorded_agent
    token = SimpleNamespace(is_set=lambda: False, was_cancelled=lambda: False, close=Mock())
    emitter = Mock()
    monkeypatch.setattr(agent, "_turn_cancel_token", lambda *a, **kw: token)
    monkeypatch.setattr("praisonaiagents.trace.context_events.get_context_emitter", lambda: emitter)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def save(**kwargs):
            entered.set()
            await release.wait()
            db.ends.append(kwargs)

        async def respond(**kwargs):
            return "answer"

        monkeypatch.setattr(db, "aon_run_end", save, raising=False)
        monkeypatch.setattr(agent, "_achat_impl", respond)
        task = asyncio.create_task(agent.achat("question"))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert len(db.starts) == len(db.ends) == 1
    assert db.starts[0]["run_id"] == db.ends[0]["run_id"]
    assert db.ends[0]["status"] == "completed"
    assert agent._active_turn_token is None
    emitter.agent_end.assert_called_once_with(agent.name)
    token.close.assert_called_once()


@pytest.mark.live
def test_real_agent_turns_record_final_outputs(tmp_path, monkeypatch):
    model = os.getenv("PRAISONAI_TEST_MODEL")
    if not model:
        pytest.skip("Set PRAISONAI_TEST_MODEL to select the live test provider")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    db = RunRecorder()
    agent = Agent(name="live-recorded", instructions="Reply in one short sentence.",
                  memory=MemoryConfig(db=db, user_id="live-test"), reflection=False, rules=False, output="silent",
                  model={"model": model, "max_tokens": 96})
    first = agent.start("Say hello.")
    second = asyncio.run(agent.achat("Say goodbye."))
    print(first)
    print(second)
    assert first.strip() and second.strip()
    assert len(db.sessions) == 1
    assert len(db.starts) == len(db.ends) == 2
    assert [row["output_content"] for row in db.ends] == [first, second]
    assert all(row["status"] == "completed" for row in db.ends)
    assert len({row["run_id"] for row in db.ends}) == 2
