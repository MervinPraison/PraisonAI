"""Registry and entry-point discovery for runtime health checks."""

from __future__ import annotations

import asyncio
import inspect
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

    def __init__(self, *, discover_plugins: bool = True) -> None:
        self._checks: Dict[str, HealthCheckProtocol] = {}
        self._protected: set[str] = set()
        self._plugins_loaded = not discover_plugins

    @staticmethod
    def _check_id(check: HealthCheckProtocol) -> Optional[str]:
        """Return the canonical ID, accepting ``id`` for compatibility."""
        return getattr(check, "check_id", None) or getattr(check, "id", None)

    def register_check(
        self, check: HealthCheckProtocol, *, protected: bool = False
    ) -> None:
        check_id = self._check_id(check)
        if not callable(getattr(check, "detect", None)):
            raise TypeError("Check must provide detect(context)")
        if not isinstance(check_id, str) or "/" not in check_id:
            raise ValueError("Health check IDs must be namespaced (for example channel/name)")
        if check_id in self._protected and not protected:
            # A mandatory built-in owns this ID; a plugin must not shadow the
            # required validation/repair. Silently keep the protected check.
            warnings.warn(
                f"Ignoring health check {check_id!r}: reserved for a built-in check",
                stacklevel=2,
            )
            return
        if check_id in self._checks and not protected:
            warnings.warn(
                f"Duplicate health check ID {check_id!r} - replacing existing check",
                stacklevel=2,
            )
        self._checks[check_id] = check
        if protected:
            self._protected.add(check_id)

    def get_checks(self) -> List[HealthCheckProtocol]:
        if not self._plugins_loaded:
            self._load_entry_points()
            self._plugins_loaded = True
        return list(self._checks.values())

    def get_check_ids(self) -> List[str]:
        """Return stable IDs after lazy plugin discovery."""
        self.get_checks()
        return list(self._checks)

    def protected_ids(self) -> List[str]:
        """Return IDs reserved for built-ins that plugins cannot shadow."""
        return list(self._protected)

    def run(
        self,
        context: Mapping[str, Any],
        *,
        fix: bool = False,
    ) -> List[HealthCheckResult]:
        results: List[HealthCheckResult] = []
        for check in self.get_checks():
            check_id = self._check_id(check) or ""
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
            residual = list(findings)
            repair_fn = getattr(check, "repair", None)
            if fix and findings and callable(repair_fn):
                try:
                    repair = repair_fn(context, findings)
                    if repair is not None and not isinstance(
                        repair, HealthRepairResult
                    ):
                        raise TypeError(
                            "Check repair must return HealthRepairResult or None"
                        )
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
                        repair=(
                            repair if isinstance(repair, HealthRepairResult) else None
                        ),
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

    async def arun(
        self,
        context: Mapping[str, Any],
        *,
        fix: bool = False,
    ) -> List[HealthCheckResult]:
        """Run checks without blocking an async caller's event loop.

        Checks may provide ``adetect`` and ``arepair`` coroutine methods.
        Synchronous implementations are isolated with ``asyncio.to_thread``.
        """

        async def _call(check, async_name: str, sync_name: str, *args):
            async_fn = getattr(check, async_name, None)
            if callable(async_fn):
                value = async_fn(*args)
                return await value if inspect.isawaitable(value) else value
            return await asyncio.to_thread(getattr(check, sync_name), *args)

        results: List[HealthCheckResult] = []
        for check in self.get_checks():
            check_id = self._check_id(check) or ""
            try:
                findings = list(await _call(check, "adetect", "detect", context))
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
            residual = list(findings)
            repair_fn = getattr(check, "arepair", None) or getattr(
                check, "repair", None
            )
            if fix and findings and callable(repair_fn):
                try:
                    repair = await _call(
                        check, "arepair", "repair", context, findings
                    )
                    if repair is not None and not isinstance(
                        repair, HealthRepairResult
                    ):
                        raise TypeError(
                            "Check repair must return HealthRepairResult or None"
                        )
                    residual = list(
                        await _call(check, "adetect", "detect", context)
                    )
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
                        repair=(
                            repair if isinstance(repair, HealthRepairResult) else None
                        ),
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
            warnings.warn(
                f"Failed to discover health checks: {exc}", stacklevel=2
            )
            return

        for entry in entries:
            try:
                provider = entry.load()
                check = provider() if callable(provider) else provider
                self.register_check(check)
            except Exception as exc:
                warnings.warn(
                    f"Failed to load health check {entry.name!r}: {exc}",
                    stacklevel=2,
                )


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


async def arun_health_checks(
    context: Mapping[str, Any], *, fix: bool = False
) -> List[HealthCheckResult]:
    return await get_health_check_registry().arun(context, fix=fix)


__all__ = [
    "HealthCheckRegistry",
    "get_health_check_registry",
    "register_health_check",
    "run_health_checks",
    "arun_health_checks",
]
