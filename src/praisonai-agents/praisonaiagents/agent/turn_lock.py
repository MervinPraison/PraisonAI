"""One turn at a time per agent (X-18): concurrent chat()/achat()/start(stream=True)
calls on one Agent interleaved its history; now each turn holds a per-agent lock
and callers queue (use separate agents for parallel conversations). A nested call
inside the agent's own turn sees it held through a context variable and does not
wait. A stream holds the lock from its first chunk until it ends, raises or is
closed (close() or GC), maybe on another thread: so a plain Lock, not an RLock.
"""

import asyncio
import contextvars
import functools
import threading
import weakref

_create_guard = threading.Lock()
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
        if loop not in locks:
            locks[loop] = asyncio.Lock()
        return locks[loop]


def serial_turn(method):
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
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        held = _held.get()
        if id(self) in held:
            return (yield from method(self, *args, **kwargs))
        lock = _thread_lock(self)
        lock.acquire()
        _held.set(held | {id(self)})
        try:
            return (yield from method(self, *args, **kwargs))
        finally:
            # Not reset(token): streams can end out of order, and a token
            # restore would drop or revive another agent's mark.
            _held.set(_held.get() - {id(self)})
            lock.release()

    return wrapper
