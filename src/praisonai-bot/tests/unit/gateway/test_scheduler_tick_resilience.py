"""The gateway scheduler tick loop survives a failing tick (issue #6035)."""

import asyncio
import tempfile

import pytest

pytest.importorskip("praisonaiagents.scheduler")

import praisonaiagents.scheduler as sched_pkg
from praisonaiagents.scheduler.store import FileScheduleStore

from praisonai_bot.gateway.server import WebSocketGateway
from praisonai_bot.scheduler.executor import ScheduledAgentExecutor


def _bare_gateway(config=None):
    gw = WebSocketGateway.__new__(WebSocketGateway)  # skip heavy __init__
    gw._agents, gw._loaded_config, gw._scheduler_task = {}, config or {}, None

    async def _deliver(*a, **k):
        return None

    gw._deliver_scheduled_result = _deliver
    return gw


async def test_tick_loop_survives_exception(monkeypatch):
    store = FileScheduleStore(store_dir=tempfile.mkdtemp())
    monkeypatch.setattr(sched_pkg, "get_default_store", lambda: store)
    calls = {"n": 0}
    orig = ScheduledAgentExecutor.tick_all

    async def flaky_tick_all(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(24, "Too many open files")
        return await orig(self)

    monkeypatch.setattr(ScheduledAgentExecutor, "tick_all", flaky_tick_all)

    gw = _bare_gateway()
    gw._start_scheduler_tick(interval=0.01)
    try:
        await asyncio.sleep(0.3)
        assert calls["n"] >= 2
        assert not gw._scheduler_task.done()
    finally:
        gw._scheduler_task.cancel()
        await asyncio.gather(gw._scheduler_task, return_exceptions=True)


def test_non_mapping_scheduler_block_uses_defaults():
    pytest.importorskip("praisonai.scheduler.run_policy")
    gw = _bare_gateway({"scheduler": ["x"]})
    policy = gw._build_run_policy()
    assert policy is not None
    assert policy.deliver_on_failure is True
    assert policy.scan_assembled_prompt is True
    from praisonai.scheduler.run_policy import DEFAULT_DENIED_TOOLSETS
    assert policy.denied_toolsets == set(DEFAULT_DENIED_TOOLSETS)
