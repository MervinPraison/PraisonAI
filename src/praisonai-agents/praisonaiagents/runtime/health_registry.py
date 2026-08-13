"""Registry and entry-point discovery for runtime health checks."""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Mapping, Optional

from .doctor_protocol import Finding
from .health_check import (
    HealthCheckProtocol,
    HealthCheckResult,
    HealthRepairResult,
)


class HealthCheckRegistry:
    """Run registered checks with failure isolation and re-validation."""

    ENTRY_POINT_GROUP = "praisonai.health_checks"

    def __init__(self) -> None:
        self._checks: Dict[str, HealthCheckProtocol] = {}
        self._plugins_loaded = False

    def register_check(self, check: HealthCheckProtocol) -> None:
        check_id = getattr(check, "id", None) or getattr(check, "check_id", None)
        if not callable(getattr(check, "detect", None)):
            raise TypeError("Check must provide detect(context)")
        if not isinstance(check_id, str) or "/" not in check_id:
            raise ValueError("Health check IDs must be namespaced (for example channel/name)")
        if check_id in self._checks:
            warnings.warn(
                f"Duplicate health check ID {check_id!r} - replacing existing check"
            )
        self._checks[check_id] = check

    def get_checks(self) -> List[HealthCheckProtocol]:
        if not self._plugins_loaded:
            self._load_entry_points()
            self._plugins_loaded = True
        return list(self._checks.values())

    def get_check_ids(self) -> List[str]:
        """Return stable IDs after lazy plugin discovery."""
        self.get_checks()
        return list(self._checks)

    def run(
        self,
        context: Mapping[str, Any],
        *,
        fix: bool = False,
    ) -> List[HealthCheckResult]:
        results: List[HealthCheckResult] = []
        self.get_checks()
        for check_id, check in self._checks.items():
            try:
                findings = list(check.detect(context))
            except Exception as exc:
                results.append(HealthCheckResult(
                    check_id=check_id,
                    findings=[],
                    residual_findings=[Finding(
                        rule_id=check_id,
                        severity="error",
                        message=f"Health check failed: {exc}",
                        context={"error": str(exc)},
                    )],
                    error=str(exc),
                ))
                continue

            repair: Optional[HealthRepairResult] = None
            residual = findings
            repair_fn = getattr(check, "repair", None)
            if fix and findings and callable(repair_fn):
                try:
                    repair = repair_fn(context, findings)
                    residual = list(check.detect(context))
                except Exception as exc:
                    residual = list(findings) + [Finding(
                        rule_id=check_id,
                        severity="error",
                        message=f"Health check repair failed: {exc}",
                        context={"error": str(exc)},
                    )]
                    results.append(HealthCheckResult(
                        check_id=check_id,
                        findings=findings,
                        residual_findings=residual,
                        repair=repair,
                        error=str(exc),
                    ))
                    continue

            results.append(HealthCheckResult(
                check_id=check_id,
                findings=findings,
                residual_findings=residual,
                repair=repair,
            ))
        return results

    def _load_entry_points(self) -> None:
        try:
            from importlib.metadata import entry_points

            discovered = entry_points()
            if hasattr(discovered, "select"):
                entries = discovered.select(group=self.ENTRY_POINT_GROUP)
            else:  # pragma: no cover - Python <3.10 compatibility
                entries = discovered.get(self.ENTRY_POINT_GROUP, [])
        except Exception as exc:  # pragma: no cover - platform metadata failure
            warnings.warn(f"Failed to discover health checks: {exc}")
            return

        for entry in entries:
            try:
                provider = entry.load()
                check = provider() if callable(provider) else provider
                self.register_check(check)
            except Exception as exc:
                warnings.warn(f"Failed to load health check {entry.name!r}: {exc}")


_default_registry: Optional[HealthCheckRegistry] = None


def get_health_check_registry() -> HealthCheckRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = HealthCheckRegistry()
    return _default_registry


def register_health_check(check: HealthCheckProtocol) -> None:
    get_health_check_registry().register_check(check)


def run_health_checks(
    context: Mapping[str, Any], *, fix: bool = False
) -> List[HealthCheckResult]:
    return get_health_check_registry().run(context, fix=fix)


__all__ = [
    "HealthCheckRegistry",
    "get_health_check_registry",
    "register_health_check",
    "run_health_checks",
]
