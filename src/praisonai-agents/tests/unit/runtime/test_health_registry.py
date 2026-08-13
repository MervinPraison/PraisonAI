"""Tests for extensible runtime health checks."""

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
