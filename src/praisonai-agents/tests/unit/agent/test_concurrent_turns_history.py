"""X-18: one Agent used from several threads or tasks keeps each turn paired.

Concurrent chat()/achat() calls on one agent used to interleave in its history
(user, user, assistant, assistant): each call sent the others' unanswered
questions as context, and replies no longer followed their questions. Turns on
one agent are now serialised; concurrent callers queue.
"""

import asyncio
import threading
import time

from praisonaiagents import Agent
from praisonaiagents.model_harness import ScriptedModel

CALLS = 3
WORKERS = 8


def _echo_slowly(req):
    time.sleep(0.03)
    return f"re: {req.last_user_message}"


def _agent():
    model = ScriptedModel([_echo_slowly] * (CALLS * WORKERS))
    return Agent(name="shared", instructions="Echo bot.", llm=model)


def _assert_paired(agent):
    history = [m for m in agent.chat_history if m.get("role") in ("user", "assistant")]
    assert len(history) == 2 * CALLS * WORKERS
    for i in range(0, len(history), 2):
        user, assistant = history[i], history[i + 1]
        assert (user["role"], assistant["role"]) == ("user", "assistant"), history[i : i + 2]
        assert assistant["content"] == f"re: {user['content']}"


def test_threads_sharing_one_agent_keep_turns_paired():
    agent = _agent()

    def worker(w):
        for c in range(CALLS):
            agent.chat(f"thread {w} call {c}")

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    _assert_paired(agent)


def test_tasks_sharing_one_agent_keep_turns_paired():
    agent = _agent()

    async def worker(w):
        for c in range(CALLS):
            await agent.achat(f"task {w} call {c}")

    async def main():
        await asyncio.gather(*(worker(w) for w in range(WORKERS)))

    asyncio.run(main())
    _assert_paired(agent)


def test_a_copied_agent_gets_its_own_turn_lock():
    import copy

    from praisonaiagents.agent.turn_lock import _thread_lock

    agent = Agent(name="copied", instructions="bot", llm="gpt-4o-mini")
    lock = _thread_lock(agent)
    clone = copy.deepcopy(agent)
    assert clone.__dict__.get("_turn_lock") is None  # built lazily on the clone's first turn
    assert _thread_lock(clone) is not lock


def test_threads_streaming_one_agent_keep_turns_paired():
    agent = _agent()

    def worker(w):
        for c in range(CALLS):
            "".join(str(chunk) for chunk in agent.start(f"stream {w} call {c}", stream=True))

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    _assert_paired(agent)


def test_an_abandoned_stream_releases_the_turn():
    agent = _agent()
    stream = agent.start("first", stream=True)
    next(iter(stream), None)  # started, then dropped half-way
    stream.close()
    assert agent.chat("second") == "re: second"  # would block forever if the lock leaked


def test_streams_ending_out_of_order_leave_no_turn_marked_held():
    from praisonaiagents.agent.turn_lock import _held

    x, y = _agent(), _agent()
    sx, sy = x.start("x", stream=True), y.start("y", stream=True)
    next(iter(sx), None)
    next(iter(sy), None)
    sx.close()  # x ends first, y second
    sy.close()
    assert _held.get() == frozenset()  # a stale mark would let x skip its lock


def test_a_stream_resumed_in_a_fresh_context_can_call_its_own_agent():
    import contextvars

    from praisonaiagents.agent.turn_lock import serial_stream_turn, serial_turn

    class Bot:
        @serial_turn
        def chat(self, prompt):
            return f"re: {prompt}"

        @serial_stream_turn
        def stream(self):
            yield "first"
            yield self.chat("fallback")  # e.g. the stream's chat() fallback

    stream = Bot().stream()
    out = {}

    def step():  # each chunk pulled in a new context copy, as thread pools do
        out.setdefault("chunks", []).append(contextvars.copy_context().run(next, stream))

    for _ in range(2):
        t = threading.Thread(target=step, daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "stream deadlocked on its own turn lock"
    assert out["chunks"] == ["first", "re: fallback"]
