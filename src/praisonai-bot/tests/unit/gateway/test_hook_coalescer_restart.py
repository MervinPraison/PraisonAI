"""Coalesced hook keys are only recorded once the burst runs (Issue #6038)."""

import asyncio

from praisonaiagents.gateway import CoalesceConfig, HookConfig

from praisonai_bot.gateway.hook_coalescer import HookCoalescer


def _hook():
    return HookConfig(
        path="github",
        message="push",
        coalesce=CoalesceConfig(group_key="{pr}", window_seconds=0.05),
    )


async def _run(dispatch_ok, close_early=False):
    settled = []

    async def dispatch(hook, payload, count):
        return dispatch_ok

    c = HookCoalescer(dispatch, settle=lambda keys, ok: settled.append((keys, ok)))
    hook = _hook()
    c.submit("k", hook, {"pr": 1}, idempotency_key="a")
    c.submit("k", hook, {"pr": 1}, idempotency_key="b")
    if close_early:
        await c.aclose()
    else:
        await asyncio.sleep(0.3)
    return settled


async def test_success_records_every_key_in_the_burst():
    assert await _run(True) == [(["a", "b"], True)]


async def test_failed_run_releases_keys():
    assert await _run(False) == [(["a", "b"], False)]


async def test_shutdown_before_run_releases_keys():
    assert await _run(True, close_early=True) == [(["a", "b"], False)]


async def test_retry_accepted_after_unrun_burst():
    """End to end with the durable store: a cancelled burst does not dedupe."""
    from praisonai_bot.bots._idempotency import SqliteIdempotencyStore
    import tempfile, os

    store = SqliteIdempotencyStore(os.path.join(tempfile.mkdtemp(), "i.sqlite"))

    def settle(keys, ok):
        for k in keys:
            store.record(k) if ok else store.release(k)

    async def dispatch(hook, payload, count):
        return True

    c = HookCoalescer(dispatch, settle=settle)
    assert store.reserve("delivery-1")
    c.submit("k", _hook(), {"pr": 1}, idempotency_key="delivery-1")
    assert not store.reserve("delivery-1")  # still pending: deduped
    await c.aclose()
    assert store.reserve("delivery-1")  # sender retry accepted
