"""
EvalPort adapter - framework-neutral interop for the eval package.

Converts PraisonAI's native eval data models to/from the EvalPort open spec
(https://github.com/adhabnr-ux/evalport), so a suite built here can run against
another tool's harness, and results can be diffed/aggregated across tools.

Mapping (1:1 with EvalPort's ``Suite`` / ``ResultSet`` concepts):

    EvalPackage <-> EvalPort Suite      (name/description/version + cases + thresholds)
    EvalCase    <-> EvalPort test case  (input / expected_output / grader refs)
    EvalReport   -> EvalPort ResultSet  (aggregate + per-case pass/score/latency)

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
from typing import Any, Dict, List

from .package import EvalCase, EvalPackage, EvalReport

EVALPORT_SPEC_VERSION = "1.0"


def _case_to_evalport(case: EvalCase) -> Dict[str, Any]:
    """Map an ``EvalCase`` to an EvalPort test-case dict.

    The native ``timeout_seconds`` is emitted as a dedicated top-level field so
    it never collides with a user-supplied ``metadata["timeout_seconds"]`` key,
    keeping round trips lossless for both.
    """
    item: Dict[str, Any] = {
        "id": case.name,
        "input": case.input,
    }
    if case.expected is not None:
        item["expected_output"] = case.expected
    if case.criteria:
        item["graders"] = list(case.criteria)
    if case.timeout_seconds is not None:
        item["timeout_seconds"] = case.timeout_seconds
    metadata = dict(case.metadata or {})
    if metadata:
        item["metadata"] = metadata
    return item


def _case_from_evalport(item: Dict[str, Any]) -> EvalCase:
    """Map an EvalPort test-case dict to an ``EvalCase``.

    Prefers the dedicated top-level ``timeout_seconds`` field; falls back to a
    ``metadata["timeout_seconds"]`` value for suites emitted by other tools,
    without mutating the caller's metadata.
    """
    metadata = dict(item.get("metadata") or {})
    if "timeout_seconds" in item:
        timeout = item["timeout_seconds"]
    else:
        timeout = metadata.get("timeout_seconds", 30.0)
    return EvalCase(
        name=item.get("id") or item.get("name") or "case",
        input=item.get("input", ""),
        expected=item.get("expected_output", item.get("expected")),
        criteria=list(item.get("graders") or item.get("criteria") or []),
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
    return {
        "evalport_version": EVALPORT_SPEC_VERSION,
        "kind": "suite",
        "name": package.name,
        "description": package.description,
        "version": package.version,
        "cases": [_case_to_evalport(c) for c in package.cases],
        "thresholds": dict(package.thresholds or {}),
        "seed": package.seed,
    }


def from_evalport(suite: Dict[str, Any]) -> EvalPackage:
    """Convert an EvalPort ``Suite`` dict to a native ``EvalPackage``.

    Args:
        suite: A spec-shaped EvalPort suite dict (e.g. from the Benchmark Hub).

    Returns:
        An ``EvalPackage`` whose cases can be run via ``EvalSuite`` /
        ``HarnessEvaluator`` as native ``EvalCase`` objects.
    """
    cases: List[EvalCase] = [_case_from_evalport(c) for c in suite.get("cases", [])]
    return EvalPackage(
        name=suite.get("name", "suite"),
        description=suite.get("description", ""),
        version=suite.get("version", "1.0.0"),
        cases=cases,
        thresholds=dict(suite.get("thresholds") or {}),
        seed=suite.get("seed"),
    )


def report_to_evalport(report: EvalReport) -> Dict[str, Any]:
    """Convert an ``EvalReport`` to an EvalPort ``ResultSet`` dict.

    Args:
        report: The aggregated report from running an eval package.

    Returns:
        A spec-shaped dict suitable for
        ``openeval.validate.validate_result_set()``.
    """
    results: List[Dict[str, Any]] = []
    for r in report.results:
        item: Dict[str, Any] = {
            "case_id": r.case_name,
            "passed": r.passed,
            "score": r.score,
            "latency_ms": r.latency_ms,
        }
        if r.actual_output is not None:
            item["actual_output"] = r.actual_output
        if r.error is not None:
            item["error"] = r.error
        if r.criteria_scores:
            item["grader_scores"] = dict(r.criteria_scores)
        if r.record is not None:
            item["record"] = r.record
        results.append(item)

    return {
        "evalport_version": EVALPORT_SPEC_VERSION,
        "kind": "result_set",
        "suite_name": report.package_name,
        "summary": {
            "total": report.total_cases,
            "passed": report.passed_cases,
            "failed": report.failed_cases,
            "pass_rate": report.pass_rate,
            "average_score": report.average_score,
            "thresholds_met": dict(report.thresholds_met or {}),
        },
        "results": results,
    }
