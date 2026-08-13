"""Tests for extensible runtime health checks."""

import os
import threading

import pytest

from praisonaiagents.runtime.doctor_protocol import Finding
from praisonaiagents.runtime.health_check import (
    HealthCheckProtocol,
    HealthRepairResult,
)
from praisonaiagents.runtime.health_registry import HealthCheckRegistry


class _RepairableCheck:
    check_id = "test/repairable"

    def __init__(self):
        self.healthy = False

    def detect(self, context):
        if self.healthy:
            return []
        return [Finding(
            rule_id=self.check_id,
            severity="error",
            message="not healthy",
            fix_description="repair it",
        )]

    def repair(self, context, findings):
        self.healthy = True
        return HealthRepairResult(changed=True, message="repaired")


def test_registry_repairs_and_revalidates():
    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(_RepairableCheck())

    result = registry.run({}, fix=True)[0]

    assert result.repaired is True
    assert result.findings
    assert result.residual_findings == []
    assert result.to_dict()["repair"]["message"] == "repaired"


def test_registry_isolates_broken_checks():
    class Broken(_RepairableCheck):
        check_id = "test/broken"

        def detect(self, context):
            raise RuntimeError("boom")

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(Broken())

    result = registry.run({})[0]

    assert result.error == "boom"
    assert result.residual_findings[0].severity == "error"


def test_registry_accepts_diagnostic_only_checks():
    class DiagnosticOnly:
        check_id = "test/diagnostic-only"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="warning",
                message="manual action required",
                fix_description="follow the integration guide",
            )]

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(DiagnosticOnly())

    result = registry.run({}, fix=True)[0]

    assert result.repair is None
    assert result.residual_findings == result.findings


def test_registry_accepts_legacy_id_alias():
    class LegacyCheck:
        id = "plugin/canonical"

        def detect(self, context):
            return []

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(LegacyCheck())

    assert registry.get_check_ids() == ["plugin/canonical"]
    assert registry.run({})[0].check_id == "plugin/canonical"


def test_protocol_uses_canonical_check_id_attribute():
    class CanonicalCheck:
        check_id = "plugin/canonical"

        def detect(self, context):
            return []

    assert isinstance(CanonicalCheck(), HealthCheckProtocol)


def test_registry_rejects_invalid_checks():
    class NoDetect:
        check_id = "test/no-detect"

    class UnnamespacedId:
        check_id = "unnamespaced"

        def detect(self, context):
            return []

    registry = HealthCheckRegistry(discover_plugins=False)

    with pytest.raises(TypeError):
        registry.register_check(NoDetect())
    with pytest.raises(ValueError):
        registry.register_check(UnnamespacedId())


def test_protected_check_cannot_be_shadowed():
    class Core:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="core saw a problem",
            )]

    class Impostor:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return []

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(Core(), protected=True)
    with pytest.warns(UserWarning):
        registry.register_check(Impostor())

    result = registry.run({})[0]

    assert result.residual_findings[0].message == "core saw a problem"


def test_protected_check_replaceable_by_protected_owner():
    class First:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="first",
            )]

    class Second:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="second",
            )]

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(First(), protected=True)
    registry.register_check(Second(), protected=True)

    assert registry.get_check_ids() == ["core/gateway/auth-token"]
    assert registry.run({})[0].residual_findings[0].message == "second"


def test_malformed_repair_result_is_isolated():
    class BadRepair:
        check_id = "test/bad-repair"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="needs repair",
            )]

        def repair(self, context, findings):
            return "not-a-repair-result"

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(BadRepair())

    result = registry.run({}, fix=True)[0]

    assert result.error is not None
    assert result.repair is None
    assert any(
        "repair failed" in finding.message for finding in result.residual_findings
    )
    assert result.to_dict()["repair"] is None


def test_registry_isolates_raising_repair():
    class BadRepair(_RepairableCheck):
        check_id = "test/raising-repair"

        def repair(self, context, findings):
            raise RuntimeError("repair boom")

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(BadRepair())

    result = registry.run({}, fix=True)[0]

    assert result.error == "repair boom"
    assert result.repaired is False
    assert any(
        "repair failed" in finding.message for finding in result.residual_findings
    )


@pytest.mark.asyncio
async def test_async_registry_prefers_async_check_methods():
    class AsyncRepairable:
        check_id = "test/async"

        def __init__(self):
            self.healthy = False

        def detect(self, context):
            raise AssertionError("sync detect must not run")

        async def adetect(self, context):
            if self.healthy:
                return []
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="not healthy",
            )]

        async def arepair(self, context, findings):
            self.healthy = True
            return HealthRepairResult(changed=True, message="repaired async")

    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(AsyncRepairable())

    result = (await registry.arun({}, fix=True))[0]

    assert result.repaired is True
    assert result.repair.message == "repaired async"


@pytest.mark.asyncio
async def test_async_registry_offloads_sync_checks():
    caller_thread = threading.get_ident()

    class SyncCheck:
        check_id = "test/sync-offload"

        def __init__(self):
            self.detect_thread = None

        def detect(self, context):
            self.detect_thread = threading.get_ident()
            return []

    check = SyncCheck()
    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(check)

    await registry.arun({})

    assert check.detect_thread is not None
    assert check.detect_thread != caller_thread


def _agent_health_fixture():
    class HealthyCheck:
        check_id = "agentic/runtime-health"

        def __init__(self):
            self.detect_calls = 0

        def detect(self, context):
            self.detect_calls += 1
            return []

    check = HealthyCheck()
    registry = HealthCheckRegistry(discover_plugins=False)
    registry.register_check(check)

    def inspect_runtime_health() -> str:
        """Inspect runtime health and return the exact registered check IDs."""
        return ", ".join(result.check_id for result in registry.run({}))

    return check, inspect_runtime_health


def test_health_check_agent_smoke(monkeypatch):
    from praisonaiagents import Agent

    check, inspect_runtime_health = _agent_health_fixture()
    agent = Agent(
        name="health-smoke",
        instructions="Inspect runtime health before answering.",
        tools=[inspect_runtime_health],
    )
    monkeypatch.setattr(
        agent,
        "chat",
        lambda prompt, **kwargs: inspect_runtime_health(),
    )

    result = agent.start("Inspect runtime health and report the check ID.")
    print(result)

    assert result == "agentic/runtime-health"
    assert check.detect_calls == 1


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)
def test_health_check_real_agentic():
    from praisonaiagents import Agent

    check, inspect_runtime_health = _agent_health_fixture()
    agent = Agent(
        name="health-agentic",
        model="gpt-4o-mini",
        instructions=(
            "Always call inspect_runtime_health before answering and include "
            "the exact check ID returned by the tool."
        ),
        tools=[inspect_runtime_health],
    )

    result = agent.start("Inspect runtime health and report the exact check ID.")
    print(result)

    assert result
    assert check.detect_calls > 0
