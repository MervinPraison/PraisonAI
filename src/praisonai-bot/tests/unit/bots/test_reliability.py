"""Tests for the gateway reliability preset (Issue #2531)."""

from __future__ import annotations

import pytest

from praisonai_bot.bots._reliability import (
    ResolvedReliability,
    normalize_reliability,
    resolve_reliability,
)


def test_unset_posture_is_safe_by_default():
    """Unset reliability is safe by default: admission ceiling + drain (#3438)."""
    r = resolve_reliability(None)
    # Snappy drain on the (unknown → loopback) bind, but a real admission
    # ceiling and bounded fair queue so a burst can't fan out unboundedly.
    assert r.drain_timeout == 5.0
    assert r.max_concurrent_runs > 0
    assert r.queue_depth > 0
    assert r.overflow_policy == "queue"


def test_unset_externally_bound_is_full_production():
    """An unset posture on a non-loopback bind resolves to production (#3438)."""
    r = resolve_reliability(None, bind_host="0.0.0.0")
    assert r.drain_timeout == 15.0
    assert r.max_concurrent_runs > 0
    assert r.queue_depth > 0
    assert r.overflow_policy == "queue"
    assert r.outbound_ordering == "strict"


def test_unset_loopback_bind_stays_snappy():
    """Loopback binds keep the ceiling but a snappy drain window (#3438)."""
    for host in ("127.0.0.1", "localhost", "::1", None):
        r = resolve_reliability(None, bind_host=host)
        assert r.drain_timeout == 5.0
        assert r.max_concurrent_runs > 0


def test_explicit_default_is_legacy_no_admission():
    """Explicit reliability='default' keeps the legacy no-ceiling posture."""
    r = resolve_reliability("default")
    assert r.drain_timeout == 5.0
    assert r.max_concurrent_runs == 0
    assert r.queue_depth == 0


def test_production_enables_drain_admission_bounded_queue():
    """The production preset composes drain + a bounded admission queue."""
    r = resolve_reliability("production")
    assert r.drain_timeout == 15.0
    assert r.max_concurrent_runs > 0
    assert r.queue_depth > 0
    # A bounded queue is the production-safe default overflow behaviour.
    assert r.overflow_policy == "queue"


def test_off_preserves_immediate_teardown():
    """reliability='off' restores today's no-drain, no-admission behaviour."""
    r = resolve_reliability("off")
    assert r.drain_timeout == 0.0
    assert r.max_concurrent_runs == 0
    assert r.queue_depth == 0


def test_explicit_fields_override_production_preset():
    """Explicit drain/ceiling always win over the preset."""
    r = resolve_reliability(
        "production", drain_timeout=30.0, max_concurrent_runs=8
    )
    assert r.drain_timeout == 30.0
    assert r.max_concurrent_runs == 8


def test_explicit_admission_policy_suppresses_preset_ceiling():
    """A caller-supplied admission policy wins; the preset adds no ceiling."""
    sentinel = object()
    r = resolve_reliability("production", admission_policy=sentinel)
    # Preset does not synthesise a numeric ceiling when a policy is explicit.
    assert r.max_concurrent_runs == 0


def test_off_respects_explicit_drain_opt_in():
    """Even with off, an explicit drain_timeout is honoured."""
    r = resolve_reliability("off", drain_timeout=12.0)
    assert r.drain_timeout == 12.0


def test_normalize_is_case_and_space_insensitive():
    assert normalize_reliability("  Production ") == "production"
    assert normalize_reliability("") is None
    assert normalize_reliability("none") is None
    assert normalize_reliability(None) is None


def test_unknown_profile_fails_fast():
    with pytest.raises(ValueError):
        resolve_reliability("bogus")
    with pytest.raises(ValueError):
        normalize_reliability("turbo")


def test_returns_dataclass():
    assert isinstance(resolve_reliability(None), ResolvedReliability)


def test_botos_reliability_production_wires_drain_and_admission():
    """BotOS(reliability='production') sets a drain window and an admission gate."""
    from praisonai_bot.bots.botos import BotOS

    os_ = BotOS(bots=[], reliability="production")
    assert os_._drain_timeout == 15.0
    assert os_._admission_gate is not None
    assert os_._admission_gate.enabled


def test_botos_reliability_off_no_drain_no_gate():
    from praisonai_bot.bots.botos import BotOS

    os_ = BotOS(bots=[], reliability="off")
    # off → immediate teardown (drain coerced to None/0) and no admission gate.
    assert not os_._drain_timeout
    assert os_._admission_gate is None


def test_botos_unset_reliability_is_safe_by_default():
    """BotOS() with no reliability arg is backpressured by default (#3438)."""
    from praisonai_bot.bots.botos import BotOS

    os_ = BotOS(bots=[])
    assert os_._drain_timeout == 5.0
    assert os_._admission_gate is not None
    assert os_._admission_gate.enabled


def test_botos_explicit_drain_overrides_reliability():
    from praisonai_bot.bots.botos import BotOS

    os_ = BotOS(bots=[], reliability="production", drain_timeout=30.0)
    assert os_._drain_timeout == 30.0


def _run_no_config_gateway_start(**start_kwargs):
    """Drive ``GatewayHandler.start`` down the no-config path with a fake
    gateway, returning the ``drain_timeout`` passed to ``stop()`` on Ctrl+C.

    Skips when the gateway's optional deps (starlette/websockets) are absent.
    """
    from unittest import mock

    try:
        from praisonai_bot.cli.features.gateway import GatewayHandler
        from praisonai_bot.gateway import WebSocketGateway  # noqa: F401
        from praisonaiagents.gateway import GatewayConfig  # noqa: F401
    except Exception:  # pragma: no cover - optional deps missing
        pytest.skip("gateway optional deps not installed")

    captured = {}

    class _FakeGateway:
        def __init__(self, *a, **k):
            self._admission_gate = None

        async def start(self):
            raise KeyboardInterrupt

        async def stop(self, drain_timeout=None):
            captured["drain_timeout"] = drain_timeout

    handler = GatewayHandler()
    with mock.patch(
        "praisonai_bot.gateway.WebSocketGateway", _FakeGateway
    ):
        handler.start(**start_kwargs)
    return captured.get("drain_timeout", "UNSET")


def test_cli_no_config_reliability_production_drains():
    """`--reliability production` (no config) drains with the preset window."""
    assert _run_no_config_gateway_start(reliability="production") == 15.0


def test_cli_no_config_explicit_drain_overrides_reliability():
    """Explicit `--drain-timeout` still wins over the preset (no config)."""
    assert (
        _run_no_config_gateway_start(reliability="production", drain_timeout=30.0)
        == 30.0
    )


def test_cli_no_config_reliability_off_immediate_teardown():
    """`--reliability off` (no config) tears down immediately (drain 0)."""
    assert _run_no_config_gateway_start(reliability="off") == 0.0


def test_cli_no_config_unset_loopback_safe_default_drains():
    """No reliability + loopback bind (no config) drains with the safe window."""
    assert _run_no_config_gateway_start(host="127.0.0.1") == 5.0


def test_cli_no_config_unset_external_bind_full_production_drain():
    """No reliability + a non-loopback bind gets the full production drain."""
    assert _run_no_config_gateway_start(host="0.0.0.0") == 15.0
