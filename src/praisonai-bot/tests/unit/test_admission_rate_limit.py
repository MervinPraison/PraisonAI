"""Per-user inbound request budget in the admission gate (Issue #6215)."""

import asyncio

import pytest

from praisonai_bot.bots._admission import (
    AdmissionGate,
    AdmissionRejected,
    build_admission_gate,
)


async def _turn(gate, user):
    async with gate.admit(session_id=user):
        return "ran"


def test_unconfigured_means_no_gate():
    assert build_admission_gate(per_user_per_minute=0) is None


def test_negative_budget_fails_fast():
    with pytest.raises(ValueError):
        build_admission_gate(per_user_per_minute=-1)


def test_over_budget_user_refused_with_retry_after_others_unaffected():
    gate = build_admission_gate(per_user_per_minute=2)
    assert gate is not None and gate.enabled

    async def run():
        assert await _turn(gate, "alice") == "ran"
        assert await _turn(gate, "alice") == "ran"
        with pytest.raises(AdmissionRejected) as exc:
            await _turn(gate, "alice")
        # A different user still has their own budget.
        assert await _turn(gate, "bob") == "ran"
        return exc.value

    rej = asyncio.run(run())
    assert rej.retry_after is not None and 1 <= rej.retry_after <= 60
    assert "try again in" in rej.message
    stats = gate.stats()
    assert stats["rate_limited"] == 1
    assert stats["per_user_per_minute"] == 2
    assert stats["in_flight"] == 0


def test_rate_limit_composes_with_concurrency_gate():
    gate = build_admission_gate(max_concurrent_runs=4, per_user_per_minute=1)
    assert gate.stats()["max_concurrent_runs"] == 4

    async def run():
        await _turn(gate, "u")
        with pytest.raises(AdmissionRejected):
            await _turn(gate, "u")

    asyncio.run(run())
    assert gate.stats()["in_flight"] == 0


def test_stale_identities_are_pruned():
    from praisonaiagents.gateway import SlidingWindowRateLimitPolicy

    pol = SlidingWindowRateLimitPolicy(max_requests=1, window_seconds=60)
    for i in range(10):
        pol.check(identity=f"u{i}", scope="ingress", now=0.0)
    AdmissionGate._prune_rate_limit_state(pol, now=120.0, cap=5)
    assert pol._windows == {}


def test_botos_kwarg_and_yaml(tmp_path):
    try:
        from praisonai_bot.bots.botos import BotOS
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("BotOS optional dependency not installed")
    assert BotOS(per_user_per_minute=5).admission_stats["per_user_per_minute"] == 5
    pytest.importorskip("yaml")
    cfg = tmp_path / "botos.yaml"
    cfg.write_text("gateway:\n  per_user_per_minute: 7\n")
    assert BotOS.from_config(str(cfg)).admission_stats["per_user_per_minute"] == 7
