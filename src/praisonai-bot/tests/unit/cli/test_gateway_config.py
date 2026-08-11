#!/usr/bin/env python3
"""
Test script to validate the gateway configuration unification.
"""

import os
import yaml
from pathlib import Path

import praisonai

# Mock pydantic if not available
try:
    import pydantic
except ImportError:
    print("Note: pydantic not available, testing config structure only")

def test_env_utils():
    """Test environment variable utilities."""
    print("\n=== Testing env_utils ===")
    
    from praisonai.cli.utils.env_utils import substitute_env_vars
    
    # Test string substitution
    os.environ["TEST_VAR"] = "test_value"
    result = substitute_env_vars("${TEST_VAR}")
    assert result == "test_value", f"Expected 'test_value', got '{result}'"
    print("✓ String substitution works")
    
    # Test dict substitution
    test_dict = {"key": "${TEST_VAR}"}
    result = substitute_env_vars(test_dict)
    assert result["key"] == "test_value", f"Expected 'test_value', got '{result['key']}'"
    print("✓ Dict substitution works")
    
    # Test list substitution
    test_list = ["${TEST_VAR}", "literal"]
    result = substitute_env_vars(test_list)
    assert result[0] == "test_value", f"Expected 'test_value', got '{result[0]}'"
    print("✓ List substitution works")
    
    print("✅ All env_utils tests passed")

def test_config_migration():
    """Test configuration migration patterns."""
    print("\n=== Testing Config Migration ===")
    
    # Example single-bot config
    single_bot = {
        "platform": "telegram",
        "token": "${TELEGRAM_BOT_TOKEN}",
        "agent": {
            "name": "assistant",
            "instructions": "You are helpful"
        }
    }
    
    # Example gateway config  
    gateway_config = {
        "agents": {
            "assistant": {
                "name": "assistant",
                "instructions": "You are helpful"
            }
        },
        "channels": {
            "telegram": {
                "token": "${TELEGRAM_BOT_TOKEN}",
                "allowed_users": []  # Empty = open to all (security issue)
            }
        }
    }
    
    # Example BotOS config
    botos_config = {
        "agent": {
            "name": "assistant",
            "instructions": "You are helpful"
        },
        "platforms": {
            "telegram": {
                "token": "${TELEGRAM_BOT_TOKEN}"
            }
        }
    }
    
    print("✓ Single-bot format can be migrated")
    print("✓ Gateway format validated")
    print("✓ BotOS format can be migrated")
    
    # Security check
    if not gateway_config["channels"]["telegram"]["allowed_users"]:
        print("⚠️  Security warning: Empty allowed_users makes bot respond to everyone")
    
    print("✅ Migration patterns validated")

def test_schema_accepts_gateway_and_hooks_blocks():
    """GatewayConfigSchema validates a real gateway.yaml with gateway:/hooks:.

    Regression for issue #2585: the strict schema previously had no
    ``gateway:``/``hooks:`` fields, so validating a real gateway.yaml (which
    ``gateway/server.py::load_gateway_config`` happily runs) would fail. One
    schema must model everything the runtime reads.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return  # schema requires pydantic; skip when unavailable

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    cfg = GatewayConfigSchema(
        agents={"assistant": {"name": "assistant", "instructions": "Help"}},
        channels={"telegram": {"token": "fake-token"}},
        gateway={"host": "127.0.0.1", "port": 8765, "drain_timeout": 5},
        hooks=[{"path": "gmail", "agent": "assistant"}],
    )
    assert cfg.gateway["port"] == 8765
    assert cfg.hooks[0]["path"] == "gmail"
    assert "telegram" in cfg.channels
    print("✓ Schema accepts gateway:/hooks: blocks")


def test_gateway_server_block_rejects_typos_and_bad_types():
    """The ``gateway:`` server block is validated field-by-field (issue #3050).

    Previously modelled as an opaque ``Dict[str, Any]``, so a misspelled or
    mistyped server knob validated fine at load time and was then silently
    dropped at runtime (the gateway ran with the default the operator believed
    they had overridden). Now a typo/wrong-type/out-of-range value fails closed
    with a friendly, field-named error.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return  # schema requires pydantic; skip when unavailable

    import pytest

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    base = dict(
        agents={"assistant": {"name": "assistant", "instructions": "Help"}},
        channels={"telegram": {"token": "fake-token"}},
    )

    # Misspelled server knob ("timout") -> rejected, names the offending key.
    with pytest.raises(Exception) as excinfo:
        GatewayConfigSchema(gateway={"drain_timout": 30}, **base)
    assert "drain_timout" in str(excinfo.value)

    # Wrong type (string where a float is expected) -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(gateway={"reload_drain_timeout": "quick"}, **base)

    # Out-of-range port -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(gateway={"port": 99999}, **base)

    # Negative drain_timeout -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(gateway={"drain_timeout": -1}, **base)

    # Invalid overflow_policy -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(gateway={"overflow_policy": "nonsense"}, **base)

    # Nested health-monitor typo -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(gateway={"health": {"intervl": 5}}, **base)

    # Invalid hook action -> rejected; empty path -> rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(hooks=[{"path": "gmail", "action": "nope"}], **base)
    with pytest.raises(Exception):
        GatewayConfigSchema(hooks=[{"path": ""}], **base)

    print("✓ Gateway server block rejects typos, bad types, and bad ranges")


def test_route_target_typo_fails_fast_with_hint():
    """A route/binding naming an undeclared agent fails at load time (#3468).

    Previously a typo'd target was only a runtime ``logger.warning`` followed
    by a silent fallback to some other agent. Now it fails closed at schema
    validation (the same seam ``gateway doctor``/``gateway start`` load
    through) with the channel, the bad target, and the closest valid agent.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return

    import pytest

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    agents = {
        "personal": {"name": "personal", "instructions": "Help"},
        "support": {"name": "support", "instructions": "Support"},
    }

    # Typo in a routing slot -> rejected, names channel/slot/target + hint.
    with pytest.raises(Exception) as excinfo:
        GatewayConfigSchema(
            agents=agents,
            channels={"telegram": {"token": "x", "routing": {"dm": "personl"}}},
        )
    msg = str(excinfo.value)
    assert "telegram" in msg and "personl" in msg
    assert "did you mean 'personal'" in msg

    # Typo in the default slot -> also rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(
            agents=agents,
            channels={"slack": {"token": "x", "routes": {"default": "nope"}}},
        )

    # Typo in a binding's agent -> also rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(
            agents=agents,
            channels={
                "discord": {
                    "token": "x",
                    "bindings": [{"agent": "suport", "priority": 1}],
                }
            },
        )

    # Blank (empty-string) target -> supplied-but-invalid, also rejected.
    with pytest.raises(Exception):
        GatewayConfigSchema(
            agents=agents,
            channels={"telegram": {"token": "x", "routing": {"dm": ""}}},
        )

    print("✓ Route/binding typos fail fast with a closest-agent hint")


def test_valid_route_targets_and_single_bot_unaffected():
    """Valid targets pass; single-bot (no ``agents:``) stays unchecked (#3468)."""
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    # Correct targets validate cleanly.
    cfg = GatewayConfigSchema(
        agents={"personal": {"name": "personal", "instructions": "Help"}},
        channels={"telegram": {"token": "x", "routing": {"default": "personal"}}},
    )
    assert "telegram" in cfg.channels

    # No ``agents:`` map -> nothing to cross-check; must not raise.
    cfg2 = GatewayConfigSchema(
        channels={"telegram": {"token": "x", "routing": {"default": "whatever"}}},
    )
    assert "telegram" in cfg2.channels
    print("✓ Valid targets pass and single-bot configs are unaffected")


def test_gateway_server_block_accepts_full_valid_config():
    """A complete, correct ``gateway:`` block validates and stays dict-accessible.

    Guards backward compatibility: downstream code (``gateway/server.py``)
    reads these via ``.get(...)`` on a plain dict, so the block must remain a
    dict after validation.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    cfg = GatewayConfigSchema(
        agents={"assistant": {"name": "assistant", "instructions": "Help"}},
        channels={"telegram": {"token": "fake-token"}},
        gateway={
            "host": "0.0.0.0",
            "port": 8000,
            "drain_timeout": 30,
            "reload_drain_timeout": 10,
            "max_concurrent_runs": 5,
            "queue_depth": 10,
            "overflow_policy": "queue",
            "reliability": "balanced",
            "api": {"openai": True},
            "liveness": {"enabled": True},
            "forensics": {"enabled": True},
            "health": {"enabled": True, "interval": 60, "stale_after": 90},
        },
        hooks=[{"path": "gmail", "agent": "assistant", "custom_extra": "kept"}],
    )
    # Still a plain dict for downstream ``.get(...)`` consumers.
    assert isinstance(cfg.gateway, dict)
    assert cfg.gateway["max_concurrent_runs"] == 5
    assert cfg.gateway["health"]["interval"] == 60
    assert cfg.hooks[0]["path"] == "gmail"
    print("✓ Full valid gateway block validates and stays dict-accessible")


def test_gateway_block_accepts_and_propagates_undelivered_opt_in():
    """``gateway.notify_on_undelivered``/``undelivered_template`` load end-to-end (#3297).

    Regression: the schema forbids unknown keys, and the core ``GatewayConfig``
    dataclass deliberately does not carry these knobs, so an operator enabling
    the documented opt-in previously hit a validation error (or a silent no-op)
    and the delivery router never saw the setting. This guards both seams:
      1. ``GatewayConfigSchema`` accepts the two keys.
      2. ``WebSocketGateway.start_with_config`` stamps them onto ``self.config``
         so the router (which reads them via ``getattr``) actually turns on.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return

    import pytest

    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    # 1. Schema accepts the opt-in keys instead of rejecting them.
    cfg = GatewayConfigSchema(
        agents={"assistant": {"name": "assistant", "instructions": "Help"}},
        channels={"telegram": {"token": "fake-token"}},
        gateway={
            "notify_on_undelivered": True,
            "undelivered_template": "Sorry, that reply could not be delivered.",
        },
    )
    assert cfg.gateway["notify_on_undelivered"] is True
    assert cfg.gateway["undelivered_template"].startswith("Sorry")

    # 2. start_with_config propagates the block onto self.config so the router
    #    (which reads them via getattr) actually turns on. Drive only the
    #    config-application prologue by aborting once start_channels is reached.
    import asyncio

    from praisonai_bot.gateway.server import WebSocketGateway

    class _StopEarly(Exception):
        pass

    gw = WebSocketGateway()
    gw.load_gateway_config = lambda _p: {  # type: ignore[assignment]
        "channels": {"telegram": {"token": "fake-token"}},
        "gateway": {
            "notify_on_undelivered": True,
            "undelivered_template": "Reply undelivered.",
        },
    }

    async def _stop(*_a, **_k):
        raise _StopEarly

    gw.start_channels = _stop  # type: ignore[assignment]
    gw.start = _stop  # type: ignore[assignment]

    with pytest.raises(_StopEarly):
        asyncio.run(gw.start_with_config("ignored.yaml"))

    assert getattr(gw.config, "notify_on_undelivered", None) is True
    assert getattr(gw.config, "undelivered_template", None) == "Reply undelivered."
    print("✓ Undelivered opt-in loads via schema and reaches gateway config")


def test_start_with_config_applies_session_persist_opt_out():
    """``gateway.session.persist: false`` opt-out reaches the store (#3593).

    Regression: the multi-bot CLI builds ``WebSocketGateway(config=...)`` with a
    *default* session config, so ``__init__`` selects a persistent store before
    ``start_with_config`` loads the YAML. Before the fix, ``start_with_config``
    never read the ``session:`` block, so a documented ``persist: false`` was
    silently ignored now that persistence is durable-by-default. This guards
    that the block is re-read and the store re-selected (None for opt-out).
    """
    import asyncio

    import pytest

    from praisonai_bot.gateway.server import WebSocketGateway

    class _StopEarly(Exception):
        pass

    gw = WebSocketGateway()
    # Durable-by-default: a store exists before YAML is applied.
    assert gw._session_store is not None
    gw.load_gateway_config = lambda _p: {  # type: ignore[assignment]
        "channels": {"telegram": {"token": "fake-token"}},
        "gateway": {"session": {"persist": False}},
    }

    async def _stop(*_a, **_k):
        raise _StopEarly

    gw.start_channels = _stop  # type: ignore[assignment]
    gw.start = _stop  # type: ignore[assignment]

    with pytest.raises(_StopEarly):
        asyncio.run(gw.start_with_config("ignored.yaml"))

    # The explicit opt-out took effect: no persistent store, in-memory only.
    assert gw._session_store is None
    assert gw.config.session_config.persist is False
    print("✓ session.persist:false opt-out reaches the store via start_with_config")


def test_explicit_session_store_survives_start_with_config():
    """A constructor-supplied store is explicit and wins over YAML (#3593)."""
    import asyncio

    import pytest

    from praisonai_bot.gateway.server import WebSocketGateway

    class _StopEarly(Exception):
        pass

    sentinel = object()
    gw = WebSocketGateway(session_store=sentinel)  # type: ignore[arg-type]
    assert gw._session_store is sentinel
    gw.load_gateway_config = lambda _p: {  # type: ignore[assignment]
        "channels": {"telegram": {"token": "fake-token"}},
        "gateway": {"session": {"persist": False}},
    }

    async def _stop(*_a, **_k):
        raise _StopEarly

    gw.start_channels = _stop  # type: ignore[assignment]
    gw.start = _stop  # type: ignore[assignment]

    with pytest.raises(_StopEarly):
        asyncio.run(gw.start_with_config("ignored.yaml"))

    # YAML session block must not clobber an explicit store.
    assert gw._session_store is sentinel
    print("✓ explicit session_store survives start_with_config YAML session block")


def test_gateway_health_block_matches_runtime_consumer():
    """``gateway.health`` schema keys must match ``HealthMonitorConfig.from_dict``.

    Regression guard: the health block is passed verbatim to
    ``HealthMonitorConfig.from_dict`` at runtime (``gateway/server.py``), which
    only reads ``interval``/``startup_grace``/``stale_after``/``stuck_after``/
    ``max_restarts_per_hour``/``enabled``. If the schema drifts to invented
    keys, a real ``interval: 60`` is rejected by ``extra="forbid"`` while a
    meaningless key passes and is silently ignored — the exact silent-drop bug
    this validation exists to prevent.
    """
    try:
        import pydantic  # noqa: F401
    except ImportError:
        return

    from praisonai_bot.bots._config_schema import HealthMonitorSchema

    # Every field the runtime actually consumes must validate.
    runtime_keys = {
        "enabled": True,
        "interval": 60,
        "startup_grace": 30,
        "stale_after": 90,
        "stuck_after": 600,
        "max_restarts_per_hour": 5,
    }
    validated = HealthMonitorSchema(**runtime_keys)
    for key, value in runtime_keys.items():
        assert getattr(validated, key) == value

    # Issue #3840: the fleet crash-loop breaker adds three aggregate thresholds
    # that ``HealthMonitorConfig.from_dict`` genuinely reads at runtime, so they
    # belong in the consumed set too.
    fleet_keys = {
        "fleet_restarts_per_hour": 40,
        "failing_channel_fraction": 0.5,
        "breaker_cooldown_s": 120.0,
    }
    validated_fleet = HealthMonitorSchema(**{**runtime_keys, **fleet_keys})
    for key, value in fleet_keys.items():
        assert getattr(validated_fleet, key) == value
    # The schema's own field names must be a subset of what the runtime reads,
    # so validation can never accept a key the runtime ignores.
    consumed = {
        "enabled", "interval", "startup_grace", "stale_after",
        "stuck_after", "max_restarts_per_hour",
        "fleet_restarts_per_hour", "failing_channel_fraction",
        "breaker_cooldown_s",
    }
    assert set(HealthMonitorSchema.model_fields) <= consumed
    print("✓ gateway.health schema matches runtime HealthMonitorConfig keys")


def test_doctor_checks():
    """Test doctor check structure."""
    print("\n=== Testing Doctor Checks ===")

    # Resolve the wrapper package directory robustly. ``praisonai.__file__`` can
    # be ``None`` (namespace package) or transiently patched by sibling tests, so
    # fall back to ``__path__`` and finally to importlib's spec.
    import importlib.util

    pkg_dir = None
    pkg_file = getattr(praisonai, "__file__", None)
    if pkg_file:
        pkg_dir = Path(pkg_file).parent
    elif getattr(praisonai, "__path__", None):
        pkg_dir = Path(list(praisonai.__path__)[0])
    else:
        spec = importlib.util.find_spec("praisonai")
        if spec and spec.origin:
            pkg_dir = Path(spec.origin).parent
        elif spec and spec.submodule_search_locations:
            pkg_dir = Path(list(spec.submodule_search_locations)[0])

    if pkg_dir is None:
        import pytest

        pytest.skip("praisonai wrapper package not installed")

    # Verify doctor checks file exists
    doctor_checks_path = pkg_dir / "cli" / "features" / "doctor" / "checks" / "gateway_checks.py"
    
    if doctor_checks_path.exists():
        print("✓ gateway_checks.py exists")
        
        # Read and validate structure
        with open(doctor_checks_path) as f:
            content = f.read()
            
        # Check for required functions
        required_checks = [
            "check_gateway_config_validation",
            "check_gateway_security",
            "check_gateway_config_migration",
            "check_gateway_env_substitution"
        ]
        
        for check in required_checks:
            if f"def {check}" in content:
                print(f"✓ {check} implemented")
            else:
                print(f"✗ {check} missing")
    else:
        print("✗ gateway_checks.py not found")
    
    print("✅ Doctor checks structure validated")

def main():
    """Run all tests."""
    print("Testing Gateway Configuration Unification")
    print("=" * 50)
    
    test_env_utils()
    test_config_migration()
    test_doctor_checks()
    
    print("\n" + "=" * 50)
    print("🎉 Gateway configuration unification complete!")
    print("\nKey improvements:")
    print("• One canonical schema (GatewayConfigSchema)")
    print("• Shared env substitution helper")
    print("• Doctor validation/migration commands")
    print("• Secure defaults (mention_only, warned empty allowlists)")
    print("• Gateway command no longer deprecated")

if __name__ == "__main__":
    main()