"""Regression tests for HealthMonitor health-check protocol dispatch.

Covers:
- Canonical HealthCheckProtocol method names (health_check / ahealth_check).
- Backward-compatible legacy method names (check_health / acheck_health).
- Plain callable health checks.
"""
import pytest

from praisonaiagents.tools.health_monitor import HealthMonitor, ServiceHealthConfig


@pytest.mark.asyncio
async def test_canonical_sync_protocol_dispatch():
    class CanonicalSync:
        def health_check(self) -> bool:
            return True

    monitor = HealthMonitor()
    monitor.add_service("svc", CanonicalSync())
    assert await monitor.check_service_health("svc") is True


@pytest.mark.asyncio
async def test_canonical_async_protocol_dispatch():
    class CanonicalAsync:
        async def ahealth_check(self) -> bool:
            return True

    monitor = HealthMonitor()
    monitor.add_service("svc", CanonicalAsync())
    assert await monitor.check_service_health("svc") is True


@pytest.mark.asyncio
async def test_legacy_sync_protocol_dispatch():
    class LegacySync:
        def check_health(self) -> bool:
            return True

    monitor = HealthMonitor()
    monitor.add_service("svc", LegacySync())
    # Previously this fell through to a nonexistent health_check() and was
    # silently marked unhealthy.
    assert await monitor.check_service_health("svc") is True


@pytest.mark.asyncio
async def test_legacy_async_protocol_dispatch():
    class LegacyAsync:
        async def acheck_health(self) -> bool:
            return True

    monitor = HealthMonitor()
    monitor.add_service("svc", LegacyAsync())
    assert await monitor.check_service_health("svc") is True


@pytest.mark.asyncio
async def test_plain_callable_dispatch():
    monitor = HealthMonitor()
    monitor.add_service("svc", lambda: True)
    assert await monitor.check_service_health("svc") is True
