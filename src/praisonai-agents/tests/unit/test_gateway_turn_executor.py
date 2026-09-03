"""Unit tests for per-session turn-execution isolation (Issue #4011).

Covers the pure, core-side turn-executor contract: the ``TurnExecutorProtocol``
and ``TurnPlacement``, the ``WorkerWedgedError`` fault signal, and the zero-cost
``InProcessTurnExecutor`` default (which must run a turn on the current loop
exactly as today and be byte-for-byte backward compatible).
"""

import asyncio
from dataclasses import FrozenInstanceError

import pytest

from praisonaiagents.gateway import (
    InProcessTurnExecutor,
    TurnExecutorProtocol,
    TurnPlacement,
    WorkerWedgedError,
)


def test_inprocess_executor_protocol_conformance():
    assert isinstance(InProcessTurnExecutor(), TurnExecutorProtocol)


def test_worker_wedged_error_is_exception():
    assert issubclass(WorkerWedgedError, Exception)


def test_turn_placement_is_frozen_value_type():
    p = TurnPlacement(session_id="s", worker_id="w", epoch=1)
    assert p == TurnPlacement(session_id="s", worker_id="w", epoch=1)
    with pytest.raises(FrozenInstanceError):
        p.epoch = 2  # frozen


def test_turn_placement_epoch_defaults_to_zero():
    p = TurnPlacement(session_id="s", worker_id="w")
    assert p.epoch == 0


@pytest.mark.asyncio
async def test_inprocess_place_returns_constant_worker():
    ex = InProcessTurnExecutor()
    p = await ex.place("sess-1")
    assert p == TurnPlacement(session_id="sess-1", worker_id="inprocess", epoch=0)


@pytest.mark.asyncio
async def test_inprocess_execute_runs_turn_on_this_loop():
    ex = InProcessTurnExecutor()
    p = await ex.place("sess-1")
    ran = []

    async def turn():
        ran.append(asyncio.get_running_loop())
        return "ok"

    out = await ex.execute_turn(p, turn)
    assert out == "ok"
    assert ran == [asyncio.get_running_loop()]


@pytest.mark.asyncio
async def test_inprocess_execute_propagates_turn_errors():
    ex = InProcessTurnExecutor()
    p = await ex.place("sess-1")

    async def turn():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await ex.execute_turn(p, turn)


@pytest.mark.asyncio
async def test_inprocess_teardown_is_noop():
    ex = InProcessTurnExecutor()
    p = await ex.place("sess-1")
    assert await ex.teardown(p, reason="wedged") is None


def test_gateway_config_executor_defaults_to_none():
    """Issue #4766: the config exposes an ``executor`` seam, unset by default
    (``None`` ⇒ in-process, today's behaviour)."""
    from praisonaiagents.gateway import GatewayConfig

    cfg = GatewayConfig()
    assert cfg.executor is None
    # ``to_dict`` reports the resolved executor for doctor/observability.
    assert cfg.to_dict()["executor"] == "inprocess"


def test_gateway_config_accepts_explicit_executor():
    from praisonaiagents.gateway import GatewayConfig

    ex = InProcessTurnExecutor()
    cfg = GatewayConfig(executor=ex)
    assert cfg.executor is ex
    assert cfg.to_dict()["executor"] == "InProcessTurnExecutor"
