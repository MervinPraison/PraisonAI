"""Extensible health-check contracts shared by runtime surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, runtime_checkable

from .doctor_protocol import Finding


@dataclass(frozen=True)
class HealthRepairResult:
    """Result returned by an optional health-check repair."""

    changed: bool
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckResult:
    """One check's detect → repair → re-validate outcome."""

    check_id: str
    findings: List[Finding]
    residual_findings: List[Finding]
    repair: Optional[HealthRepairResult] = None
    error: Optional[str] = None

    @property
    def repaired(self) -> bool:
        return bool(self.repair and self.repair.changed and not self.residual_findings)

    def to_dict(self) -> Dict[str, Any]:
        def _finding(value: Finding) -> Dict[str, Any]:
            return {
                "rule_id": value.rule_id,
                "severity": value.severity,
                "message": value.message,
                "fix_description": value.fix_description,
                "context": value.context,
            }

        return {
            "id": self.check_id,
            "findings": [_finding(item) for item in self.findings],
            "repair": (
                {
                    "changed": self.repair.changed,
                    "message": self.repair.message,
                    "details": dict(self.repair.details),
                }
                if self.repair
                else None
            ),
            "residual_findings": [
                _finding(item) for item in self.residual_findings
            ],
            "repaired": self.repaired,
            "error": self.error,
        }


@runtime_checkable
class HealthCheckProtocol(Protocol):
    """Minimum protocol implemented by runtime health checks.

    A check may additionally expose ``repair(context, findings)``.  Keeping
    repair outside the required protocol lets diagnostic-only integrations
    participate without pretending that every problem is safe to automate.
    """

    @property
    def check_id(self) -> str:
        """Stable namespaced identifier for this check.

        The registry also accepts ``id`` as a compatibility alias for checks
        written against the first version of this contract.
        """
        ...

    def detect(self, context: Mapping[str, Any]) -> List[Finding]:
        """Return current health findings without mutating external state."""
        ...

__all__ = [
    "HealthCheckProtocol",
    "HealthCheckResult",
    "HealthRepairResult",
]
