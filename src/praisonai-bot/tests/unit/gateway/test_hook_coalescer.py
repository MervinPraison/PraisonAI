"""Tests for gateway hook burst coalescing runtime (Issue #5867)."""

import asyncio

from praisonaiagents.gateway import CoalesceConfig, HookConfig

from praisonai_bot.gateway.hook_coalescer import HookCoalescer


def _hook(window=0.05, max_wait=10.0):
    return HookConfig(
        path="github",
        message="push {sha}",
        coalesce=CoalesceConfig(
            group_key="{pr}", window_seconds=window, max_wait_seconds=max_wait
        ),
    )


async def test_burst_collapses_into_one_run_with_latest_payload():
    runs = []

    async def dispatch(hook, payload, count):
        runs.append((payload, count))

    c = HookCoalescer(dispatch)
    hook = _hook()
    for i in range(5):
        assert c.submit(hook.resolve_coalesce_key({"pr": 1}), hook,
                        {"pr": 1, "sha": i}) == i + 1
    c.submit(hook.resolve_coalesce_key({"pr": 2}), hook, {"pr": 2, "sha": "x"})
    await asyncio.sleep(0.3)
    assert sorted(runs, key=lambda r: r[0]["pr"]) == [
        ({"pr": 1, "sha": 4}, 5),
        ({"pr": 2, "sha": "x"}, 1),
    ]
    assert len(c) == 0


async def test_max_wait_bounds_a_steady_stream():
    runs = []

    async def dispatch(hook, payload, count):
        runs.append(count)

    c = HookCoalescer(dispatch)
    hook = _hook(window=0.1, max_wait=0.15)
    for _ in range(10):  # keeps the quiet window from ever elapsing
        c.submit("k", hook, {"pr": 1})
        await asyncio.sleep(0.03)
    await asyncio.sleep(0.2)
    assert len(runs) >= 2  # dispatched before the stream ended
    assert sum(runs) == 10


async def test_aclose_cancels_pending():
    runs = []

    async def dispatch(hook, payload, count):
        runs.append(count)

    c = HookCoalescer(dispatch)
    c.submit("k", _hook(window=5, max_wait=5), {"pr": 1})
    await c.aclose()
    assert len(c) == 0 and runs == []


async def test_gateway_run_hook_notes_absorbed_events():
    from praisonai_bot.gateway.server import WebSocketGateway

    gw = WebSocketGateway()
    seen = []

    class _Agent:
        pass

    async def _turn(agent, message):
        seen.append(message)
        return "ok"

    gw._agents = {"a": _Agent()}
    gw._dispatch_agent_turn = _turn
    hook = _hook()
    await gw._run_hook(hook, {"sha": "abc"}, coalesced=3)
    await gw._run_hook(hook, {"sha": "abc"})
    assert seen[0].startswith("[3 events coalesced")
    assert "coalesced" not in seen[1]

    # The lazily-built coalescer dispatches through _run_hook.
    c = gw._get_hook_coalescer()
    c.submit("k", hook, {"sha": "1"})
    c.submit("k", hook, {"sha": "2"})
    await asyncio.sleep(0.3)
    assert seen[-1].startswith("[2 events coalesced")


async def test_pending_group_cap_rejects_new_groups():
    async def dispatch(hook, payload, count):
        pass

    c = HookCoalescer(dispatch, max_groups=1)
    hook = _hook(window=5.0)
    assert c.submit("a", hook, {}) == 1
    assert c.submit("b", hook, {}) is None
    assert c.submit("a", hook, {}) == 2  # existing group still absorbs
    await c.aclose()


async def test_aclose_cancels_in_progress_run():
    started = asyncio.Event()
    cancelled = []

    async def dispatch(hook, payload, count):
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    c = HookCoalescer(dispatch)
    hook = _hook(window=0.01)
    c.submit("a", hook, {})
    await asyncio.wait_for(started.wait(), 1)
    assert len(c) == 0  # group left the buffer, run is in progress
    await c.aclose()
    assert cancelled == [True]


def test_hook_schema_rejects_invalid_coalesce_settings():
    import pytest
    from pydantic import ValidationError

    from praisonai_bot.bots._config_schema import HookSchema

    HookSchema(path="gh", coalesce={"group_key": "{pr}"})
    for bad in (
        {"group_key": "{pr}", "window_seconds": 0},
        {"group_key": "  "},
        {"group_key": "{pr}", "window_seconds": 60, "max_wait_seconds": 10},
        {"group_key": "{pr}", "window_seconds": float("inf")},
        {"group_key": "{pr}", "window_sec": 5},
    ):
        with pytest.raises(ValidationError):
            HookSchema(path="gh", coalesce=bad)
