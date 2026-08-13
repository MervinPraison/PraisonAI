"""Tests for extensible runtime health checks."""

import warnings

from praisonaiagents.runtime.doctor_protocol import Finding
from praisonaiagents.runtime.health_check import HealthRepairResult
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
    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
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

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
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

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
    registry.register_check(DiagnosticOnly())

    result = registry.run({}, fix=True)[0]

    assert result.repair is None
    assert result.residual_findings == result.findings


def test_registry_accepts_canonical_id_attribute():
    class CanonicalCheck:
        id = "plugin/canonical"

        def detect(self, context):
            return []

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
    registry.register_check(CanonicalCheck())

    assert registry.get_check_ids() == ["plugin/canonical"]
    assert registry.run({})[0].check_id == "plugin/canonical"


def test_protected_check_cannot_be_shadowed():
    """A plugin re-using a protected core ID must not override it (Greptile P1)."""
    class CoreCheck:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return []

    class ImpostorPlugin:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="should never run",
            )]

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
    core = CoreCheck()
    registry.register_check(core, protected=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        registry.register_check(ImpostorPlugin())

    assert registry.get_check_ids() == ["core/gateway/auth-token"]
    assert registry._checks["core/gateway/auth-token"] is core
    assert any("reserved" in str(w.message) for w in caught)


def test_protected_check_replaceable_by_protected_owner():
    """The owning surface may re-register its own protected check idempotently."""
    class CoreCheck:
        check_id = "core/gateway/auth-token"

        def detect(self, context):
            return []

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
    first = CoreCheck()
    second = CoreCheck()
    registry.register_check(first, protected=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        registry.register_check(second, protected=True)

    assert registry._checks["core/gateway/auth-token"] is second
    assert not caught


def test_malformed_repair_result_is_isolated():
    """A repair returning a non-HealthRepairResult must not crash rendering (P2)."""
    class BadRepair:
        check_id = "plugin/bad-repair"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="broken",
            )]

        def repair(self, context, findings):
            return {"changed": True}  # wrong type on purpose

    registry = HealthCheckRegistry()
    registry._plugins_loaded = True
    registry.register_check(BadRepair())

    result = registry.run({}, fix=True)[0]

    assert result.error is not None
    assert "HealthRepairResult" in result.error
    assert result.repair is None
    # to_dict must not raise on a malformed repair value.
    payload = result.to_dict()
    assert payload["repair"] is None
    assert payload["repaired"] is False
