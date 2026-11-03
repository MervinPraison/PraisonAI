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


@pytest.mark.parametrize("bad", [0.5, -0.5, 1.5, "0.5", "abc", True, -1])
def test_fractional_or_invalid_budget_rejected(bad):
    with pytest.raises(ValueError):
        build_admission_gate(per_user_per_minute=bad)


def test_botos_yaml_fractional_budget_rejected(tmp_path):
    try:
        from praisonai_bot.bots.botos import BotOS
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("BotOS optional dependency not installed")
    pytest.importorskip("yaml")
    cfg = tmp_path / "botos.yaml"
    cfg.write_text("gateway:\n  per_user_per_minute: 0.5\n")
    with pytest.raises(ValueError):
        BotOS.from_config(str(cfg))
    with pytest.raises(ValueError):
        BotOS(per_user_per_minute=0.5)


def test_rate_key_shared_across_new_sessions():
    """A caller cannot reset the budget by switching conversation ids."""
    gate = build_admission_gate(per_user_per_minute=1)

    async def run():
        async with gate.admit(session_id="conv-1", rate_key="ip:1.2.3.4"):
            pass
        with pytest.raises(AdmissionRejected):
            async with gate.admit(session_id="conv-2", rate_key="ip:1.2.3.4"):
                pass

    asyncio.run(run())


def test_prune_runs_at_bounded_interval(monkeypatch):
    gate = build_admission_gate(per_user_per_minute=5)
    calls = []
    monkeypatch.setattr(
        AdmissionGate, "_prune_rate_limit_state",
        staticmethod(lambda pol, now, cap=4096: calls.append(now)),
    )
    for i in range(50):
        gate._check_rate_limit(f"user-{i}")
    assert len(calls) == 1


def test_set_rate_limit_policy_swaps_budget_in_place():
    from praisonai_bot.bots._admission import build_rate_limit_policy

    gate = build_admission_gate(max_concurrent_runs=4)
    gate.set_rate_limit_policy(build_rate_limit_policy(1))
    assert gate.stats()["per_user_per_minute"] == 1

    async def run():
        await _turn(gate, "u")
        with pytest.raises(AdmissionRejected):
            await _turn(gate, "u")

    asyncio.run(run())
    gate.set_rate_limit_policy(build_rate_limit_policy(0))
    assert gate.stats()["per_user_per_minute"] == 0
    assert asyncio.run(_turn(gate, "u")) == "ran"


def test_gateway_reload_applies_budget():
    try:
        from praisonai_bot.gateway.server import WebSocketGateway
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("gateway optional dependency not installed")
    gw = WebSocketGateway.__new__(WebSocketGateway)
    gw._admission_gate = None
    gw._apply_rate_policy(
        gw._rate_policy_from_config({"gateway": {"per_user_per_minute": 3}})
    )
    assert gw._admission_gate.stats()["per_user_per_minute"] == 3
    gw._apply_rate_policy(gw._rate_policy_from_config({"gateway": {}}))
    assert gw._admission_gate.stats()["per_user_per_minute"] == 0
    with pytest.raises(ValueError):
        gw._rate_policy_from_config({"gateway": {"per_user_per_minute": 0.5}})


def test_api_rate_key_ignores_session_header():
    try:
        from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("gateway optional dependency not installed")

    class _Req:
        def __init__(self, headers, host="10.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    a = GatewayApiEndpoints._rate_key(_Req({"x-session-id": "one"}))
    b = GatewayApiEndpoints._rate_key(_Req({"x-session-id": "two"}))
    assert a == b == "ip:10.0.0.1"
    tok = GatewayApiEndpoints._rate_key(
        _Req({"authorization": "Bearer secret-token"}), "secret-token"
    )
    assert tok.startswith("token:") and "secret" not in tok


def test_api_rate_key_rotating_unvalidated_bearer_shares_ip_budget():
    """An unvalidated bearer (auth open, or wrong token) cannot mint budgets."""
    try:
        from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("gateway optional dependency not installed")

    class _Req:
        def __init__(self, headers, host="10.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    for configured in (None, "", "real-token"):
        keys = {
            GatewayApiEndpoints._rate_key(
                _Req({"authorization": f"Bearer rotate-{i}"}), configured
            )
            for i in range(5)
        }
        assert keys == {"ip:10.0.0.1"}


def test_api_rate_key_missing_peer_never_falls_back_to_session():
    try:
        from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("gateway optional dependency not installed")

    class _Req:
        headers = {"x-session-id": "chosen"}
        client = None

    assert GatewayApiEndpoints._rate_key(_Req()) == "ip:unknown"

    gate = build_admission_gate(per_user_per_minute=1)

    async def run():
        async with gate.admit(session_id="conv-1", rate_key="ip:unknown"):
            pass
        with pytest.raises(AdmissionRejected):
            async with gate.admit(session_id="conv-2", rate_key="ip:unknown"):
                pass

    asyncio.run(run())


def test_ws_rate_key_missing_peer_is_shared():
    try:
        from praisonai_bot.gateway.server import WebSocketGateway
    except ModuleNotFoundError:  # pragma: no cover - optional deps
        pytest.skip("gateway optional dependency not installed")
    gw = WebSocketGateway.__new__(WebSocketGateway)
    gw._clients = {}
    assert gw._client_rate_key(None) == "ip:unknown"
    assert gw._client_rate_key("gone") == "ip:unknown"
