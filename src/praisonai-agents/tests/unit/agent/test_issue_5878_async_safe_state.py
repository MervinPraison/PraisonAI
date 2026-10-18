"""Regression tests for Issue #5878: AsyncSafeState lock safety."""
import asyncio
import copy
import threading

from praisonaiagents.agent.async_safety import AsyncSafeState


def test_concurrent_with_state_is_thread_safe():
    state = AsyncSafeState([])
    errors = []
    threads_n, iters = 8, 1000

    def worker():
        try:
            for _ in range(iters):
                with state as value:
                    value.append(1)
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(state.value) == threads_n * iters
    assert not state._lock._thread_lock.locked()


def test_nested_with_state_releases_lock():
    state = AsyncSafeState([])
    with state:
        with state:
            pass
        assert state._lock._thread_lock.locked()
    assert not state._lock._thread_lock.locked()


def test_with_state_works_on_deepcopy():
    clone = copy.deepcopy(AsyncSafeState([1]))
    with clone as value:
        value.append(2)
    assert clone.value == [1, 2]
    assert not clone._lock._thread_lock.locked()


def test_async_lock_uncontended_and_contended():
    state = AsyncSafeState([])

    async def main():
        async with state.async_lock() as value:
            value.append("fast")
        # Contended: a sync holder on another thread forces the executor path.
        held, release = threading.Event(), threading.Event()

        def holder():
            with state.lock():
                held.set()
                release.wait()

        t = threading.Thread(target=holder)
        t.start()
        held.wait()
        asyncio.get_running_loop().call_later(0.05, release.set)
        async with state.async_lock() as value:
            value.append("slow")
        t.join()

    asyncio.run(main())
    assert state.value == ["fast", "slow"]
    assert not state._lock._thread_lock.locked()
