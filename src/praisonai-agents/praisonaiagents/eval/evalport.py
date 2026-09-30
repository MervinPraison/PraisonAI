"""
EvalPort adapter - framework-neutral interop for the eval package.

Converts PraisonAI's native eval data models to/from the EvalPort open spec
(https://github.com/adhabnr-ux/evalport), so a suite built here can run against
another tool's harness, and results can be diffed/aggregated across tools.

Mapping (1:1 with EvalPort's ``Suite`` / ``ResultSet`` concepts):

    EvalPackage <-> EvalPort Suite      (id/name/description + test_cases + graders)
    EvalCase    <-> EvalPort TestCase   (id / input / expected_output / grader refs)
    EvalReport   -> EvalPort ResultSet  (summary + per-case grader_results)

PraisonAI-only fields with no EvalPort slot (package version, thresholds, seed,
per-criterion scores, trajectory records, ...) are kept under the ``praisonai``
key of the relevant ``metadata`` object so round trips stay lossless.

Design: this module is intentionally **dependency-free**. It emits and consumes
plain spec-shaped dicts (JSON), so the core SDK does not take on ``evalport-sdk``
as a dependency. Callers who want schema validation can pass the returned dict to
``openeval.validate.validate_suite()`` / ``validate_result_set()`` themselves.

Example:
    >>> from praisonaiagents.eval import EvalPackage, EvalCase
    >>> from praisonaiagents.eval import to_evalport, from_evalport, report_to_evalport
    >>> pkg = EvalPackage(name="support", cases=[
    ...     EvalCase(name="refund", input="refund policy?", expected="30 days")
    ... ], thresholds={"accuracy": 0.9})
    >>> suite = to_evalport(pkg)          # EvalPackage -> EvalPort Suite dict
    >>> pkg2 = from_evalport(suite)       # EvalPort Suite dict -> EvalPackage
    >>> pkg2.name == pkg.name
    True
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .package import EvalCase, EvalPackage, EvalReport

# EvalPort spec version the emitted documents conform to (semver, per spec).
EVALPORT_SPEC_VERSION = "1.0.0-rc.5"

# Grader that carries PraisonAI's own per-case verdict (EvalResult.passed/score).
# EvalPort requires every test case to reference at least one grader.
VERDICT_GRADER_ID = "praisonai_verdict"
_HANDLER = "praisonaiagents.eval"
_META_KEY = "praisonai"


def _grader_def(grader_id: str, description: str) -> Dict[str, Any]:
    return {
        "id": grader_id,
        "type": "custom",
        "params": {"handler": _HANDLER},
        "description": description,
    }


def _case_to_evalport(case: EvalCase) -> Dict[str, Any]:
    """Map an ``EvalCase`` to an EvalPort TestCase dict.

    ``criteria`` become grader references (defined at suite level); a case
    without criteria references the verdict grader. ``timeout_seconds`` maps to
    the spec's ``timeout_ms``; user ``metadata`` is passed through untouched.
    """
    item: Dict[str, Any] = {
        "id": case.name,
        "input": case.input,
        "graders": list(case.criteria) or [VERDICT_GRADER_ID],
    }
    if case.expected is not None:
        item["expected_output"] = case.expected
    if case.timeout_seconds is not None and case.timeout_seconds > 0:
        item["timeout_ms"] = max(1, int(round(case.timeout_seconds * 1000)))
    if case.metadata:
        item["metadata"] = dict(case.metadata)
    return item


def _case_from_evalport(item: Dict[str, Any]) -> EvalCase:
    """Map an EvalPort TestCase dict to an ``EvalCase``.

    Reads ``timeout_ms`` (spec); falls back to a legacy top-level or
    ``metadata["timeout_seconds"]`` value, without mutating caller metadata.
    """
    metadata = dict(item.get("metadata") or {})
    if "timeout_ms" in item:
        timeout = item["timeout_ms"] / 1000.0
    elif "timeout_seconds" in item:
        timeout = item["timeout_seconds"]
    else:
        timeout = metadata.get("timeout_seconds", 30.0)
    criteria = []
    for g in item.get("graders") or item.get("criteria") or []:
        gid = g.get("id") if isinstance(g, dict) else g
        if gid and gid != VERDICT_GRADER_ID:
            criteria.append(gid)
    return EvalCase(
        name=item.get("id") or item.get("name") or "case",
        input=item.get("input", ""),
        expected=item.get("expected_output", item.get("expected")),
        criteria=criteria,
        metadata=metadata,
        timeout_seconds=timeout,
    )


def to_evalport(package: EvalPackage) -> Dict[str, Any]:
    """Convert an ``EvalPackage`` to an EvalPort ``Suite`` dict.

    Args:
        package: The native PraisonAI eval package.

    Returns:
        A spec-shaped dict suitable for ``openeval.validate.validate_suite()``.
    """
    criteria = dict.fromkeys(c for case in package.cases for c in case.criteria)
    criteria.pop(VERDICT_GRADER_ID, None)
    graders = [_grader_def(VERDICT_GRADER_ID, "PraisonAI per-case verdict (EvalResult.passed/score)")]
    graders += [_grader_def(c, f"PraisonAI criterion: {c}") for c in criteria]

    suite: Dict[str, Any] = {
        "version": EVALPORT_SPEC_VERSION,
        "id": package.name,
        "name": package.name,
        "graders": graders,
        "test_cases": [_case_to_evalport(c) for c in package.cases],
        "metadata": {
            _META_KEY: {
                "version": package.version,
                "thresholds": dict(package.thresholds or {}),
                "seed": package.seed,
            }
        },
    }
    if package.description:
        suite["description"] = package.description
    return suite


def from_evalport(suite: Dict[str, Any]) -> EvalPackage:
    """Convert an EvalPort ``Suite`` dict to a native ``EvalPackage``.

    Args:
        suite: A spec-shaped EvalPort suite dict (e.g. from the Benchmark Hub).

    Returns:
        An ``EvalPackage`` whose cases can be run via ``EvalSuite`` /
        ``HarnessEvaluator`` as native ``EvalCase`` objects.
    """
    items = suite.get("test_cases", suite.get("cases", []))
    cases: List[EvalCase] = [_case_from_evalport(c) for c in items]
    meta = (suite.get("metadata") or {}).get(_META_KEY) or {}
    legacy = "evalport_version" in suite  # documents emitted before spec alignment
    return EvalPackage(
        name=suite.get("name") or suite.get("id") or "suite",
        description=suite.get("description", ""),
        version=meta.get("version") or (suite.get("version") if legacy else None) or "1.0.0",
        cases=cases,
        thresholds=dict(meta.get("thresholds") or suite.get("thresholds") or {}),
        seed=meta.get("seed", suite.get("seed")),
    )


def _unit_score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return min(1.0, max(0.0, float(value)))


def _runner_info() -> Dict[str, str]:
    runner = {"name": "praisonaiagents"}
    try:
        from importlib.metadata import version

        runner["version"] = version("praisonaiagents")
    except Exception:
        pass
    return runner


def report_to_evalport(
    report: EvalReport,
    *,
    run_id: Optional[str] = None,
    started_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert an ``EvalReport`` to an EvalPort ``ResultSet`` dict.

    Args:
        report: The aggregated report from running an eval package.
        run_id: Unique run identifier (defaults to a random UUID).
        started_at: RFC 3339 run start time (defaults to now, UTC).

    Returns:
        A spec-shaped dict suitable for
        ``openeval.validate.validate_result_set()``.
    """
    results: List[Dict[str, Any]] = []
    for r in report.results:
        grader: Dict[str, Any] = {
            "grader_id": VERDICT_GRADER_ID,
            "type": "custom",
            "score": _unit_score(r.score),
            "passed": bool(r.passed),
        }
        if grader["score"] is None:
            grader["passed"] = False  # spec: null score means "not verified"
        elif grader["score"] != r.score:
            grader["metadata"] = {"openeval.raw_score": r.score}  # clamped

        item: Dict[str, Any] = {
            "test_case_id": r.case_name,
            "passed": grader["passed"],
            "grader_results": [grader],
        }
        if r.actual_output is not None:
            item["actual_output"] = str(r.actual_output)
        if r.latency_ms is not None and r.latency_ms >= 0:
            item["duration_ms"] = int(round(r.latency_ms))
        if r.error is not None:
            item["error"] = {"type": "runner_error", "message": str(r.error)}
        extra: Dict[str, Any] = {}
        if r.criteria_scores:
            extra["criteria_scores"] = dict(r.criteria_scores)
        if r.record is not None:
            extra["record"] = r.record
        if extra:
            item["metadata"] = {_META_KEY: extra}
        results.append(item)

    summary: Dict[str, Any] = {
        "total": report.total_cases,
        "passed": report.passed_cases,
        "failed": report.failed_cases,
        "pass_rate": report.pass_rate,
    }
    meta: Dict[str, Any] = {"thresholds_met": dict(report.thresholds_met or {})}
    avg = _unit_score(report.average_score)
    if avg is not None:
        summary["avg_score"] = avg
        if avg != report.average_score:
            meta["average_score"] = report.average_score  # clamped

    return {
        "version": EVALPORT_SPEC_VERSION,
        "suite_id": report.package_name,
        "run_id": run_id or uuid.uuid4().hex,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "runner": _runner_info(),
        "results": results,
        "summary": summary,
        "metadata": {_META_KEY: meta},
    }
