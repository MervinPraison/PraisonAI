"""One turn at a time per agent.

An ``Agent`` is one conversation. When several threads or asyncio tasks called
``chat()``/``achat()`` on the same agent at once, their messages interleaved in
its history (user, user, assistant, assistant): each call sent the others'
unanswered questions as context and replies no longer followed their
questions. These decorators hold a per-agent lock for the whole turn, so
concurrent callers queue. Use separate agents (or ``clone_for_channel``) for
conversations that should run in parallel.

A nested call on the same agent inside its own turn (a tool, a guardrail retry,
``achat`` falling back to ``chat`` in a worker thread) sees the turn already
held through a context variable and does not wait for itself. That flag, not
lock re-entrancy, makes nesting safe, so the thread lock is a plain ``Lock``:
a streamed turn may be closed from another thread (or by garbage collection),
and only a plain lock can be released there.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
import weakref

_create_guard = threading.Lock()
# ids of the agents whose turn this context already holds.
_held = contextvars.ContextVar("praisonai_agent_turn_held", default=frozenset())


def _thread_lock(agent) -> threading.Lock:
    lock = agent.__dict__.get("_turn_lock")
    if lock is None:
        with _create_guard:
            lock = agent.__dict__.get("_turn_lock")
            if lock is None:
                lock = threading.Lock()
                object.__setattr__(agent, "_turn_lock", lock)
    return lock


def _loop_lock(agent) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with _create_guard:
        locks = agent.__dict__.get("_turn_loop_locks")
        if locks is None:
            locks = weakref.WeakKeyDictionary()
            object.__setattr__(agent, "_turn_loop_locks", locks)
        lock = locks.get(loop)
        if lock is None:
            lock = locks[loop] = asyncio.Lock()
    return lock


def serial_turn(method):
    """Run a sync turn method while holding the agent's turn lock."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        held = _held.get()
        if id(self) in held:
            return method(self, *args, **kwargs)
        with _thread_lock(self):
            token = _held.set(held | {id(self)})
            try:
                return method(self, *args, **kwargs)
            finally:
                _held.reset(token)

    return wrapper


def serial_aturn(method):
    """Run an async turn method while holding the agent's per-loop turn lock."""

    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        held = _held.get()
        if id(self) in held:
            return await method(self, *args, **kwargs)
        async with _loop_lock(self):
            token = _held.set(held | {id(self)})
            try:
                return await method(self, *args, **kwargs)
            finally:
                _held.reset(token)

    return wrapper


def serial_stream_turn(method):
    """Hold the agent's turn lock for the life of a streaming generator.

    The lock is taken when the first chunk is requested and released when the
    stream ends, raises, or is closed (``close()``, or garbage collection of a
    dropped generator).
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        held = _held.get()
        if id(self) in held:
            return (yield from method(self, *args, **kwargs))
        lock = _thread_lock(self)
        lock.acquire()
        token = _held.set(held | {id(self)})
        try:
            return (yield from method(self, *args, **kwargs))
        finally:
            try:
                _held.reset(token)
            except ValueError:  # closed from another context (GC, another thread)
                pass
            lock.release()

    return wrapper
