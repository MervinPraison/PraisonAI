"""
HarnessEvaluator - Bridge between the Interactive Test Harness and the eval pipeline.

This module scores harness *trace* artifacts (tool traces, produced files, optional
rubric-judge scores) and maps CSV-driven harness scenarios into ``EvalCase`` /
``EvalResult`` objects so harness runs can be aggregated inside ``EvalSuite`` and
exported as an ``EvalReport``.

It is intentionally lightweight and dependency-free: it consumes a plain dict/JSON
trace (as emitted by ``interactive_test_harness`` / ``csv_test_runner``) rather than
importing the heavy CLI. This keeps the core SDK protocol-driven while giving the
wrapper CLI a stable scoring contract.

Example:
    >>> from praisonaiagents.eval import HarnessEvaluator
    >>> trace = {
    ...     "tool_calls": [{"name": "read_file"}, {"name": "write_file"}],
    ...     "artifacts": ["out.txt"],
    ...     "tool_schema": {"read_file": {...}, "write_file": {...}},
    ...     "judge_score": 9.0,
    ... }
    >>> evaluator = HarnessEvaluator(
    ...     trace=trace,
    ...     required_artifacts=["out.txt"],
    ...     name="smoke_scenario",
    ... )
    >>> result = evaluator.run(print_summary=True)
    >>> result.passed
    True
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

from .base import BaseEvaluator
from .results import HarnessResult


def harness_row_to_eval_case(row: Dict[str, Any]) -> "Any":
    """Map a CSV harness scenario row to an ``EvalCase``.

    The CSV schema used by the interactive test harness uses ``id``/``prompt``
    columns with optional ``fixture`` and ``rubric`` metadata. This adapter
    normalizes those into the eval package's ``EvalCase`` shape.

    Args:
        row: A dict representing a single CSV row (e.g. from ``csv.DictReader``).

    Returns:
        An ``EvalCase`` with harness metadata preserved.
    """
    from .package import EvalCase

    name = row.get("id") or row.get("name") or row.get("scenario") or "harness_case"
    prompt = row.get("prompt") or row.get("input") or ""

    metadata: Dict[str, Any] = {"source": "harness"}
    if row.get("fixture"):
        metadata["fixture"] = row["fixture"]
    if row.get("rubric"):
        metadata["rubric"] = row["rubric"]

    criteria: List[str] = []
    rubric = row.get("rubric")
    if rubric:
        criteria = [rubric]

    return EvalCase(
        name=str(name),
        input=str(prompt),
        expected=row.get("expected"),
        criteria=criteria,
        metadata=metadata,
    )


def _schema_hash(tool_schema: Optional[Dict[str, Any]]) -> Optional[str]:
    """Deterministic hash of the tool-definition schema for parity checks."""
    if not tool_schema:
        return None
    try:
        canonical = json.dumps(tool_schema, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = str(sorted(tool_schema.keys()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class HarnessEvaluator(BaseEvaluator):
    """Score an Interactive Test Harness trace and produce a unified result.

    Metrics scored:
        - Tool call count (informational; ``min_tool_calls`` optional gate)
        - Schema consistency (hash of tool definitions vs ``expected_schema_hash``)
        - Artifact completeness (all ``required_artifacts`` present)
        - Judge score (optional rubric score passed through from the CSV runner)

    Args:
        trace: Harness trace dict (tool_calls, artifacts, tool_schema, judge_score).
        required_artifacts: Artifact paths/names that must be present to pass.
        min_tool_calls: Minimum number of tool calls required (0 = no gate).
        expected_schema_hash: If set, the trace's tool-schema hash must match.
        judge_threshold: Judge score (0-10) at/above which the judge gate passes.
        name: Optional evaluation name.
        save_results_path: Optional path to persist the result JSON.
        verbose: Enable verbose logging.
    """

    def __init__(
        self,
        trace: Dict[str, Any],
        required_artifacts: Optional[List[str]] = None,
        min_tool_calls: int = 0,
        expected_schema_hash: Optional[str] = None,
        judge_threshold: float = 7.0,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        self.trace = trace or {}
        self.required_artifacts = required_artifacts or []
        self.min_tool_calls = min_tool_calls
        self.expected_schema_hash = expected_schema_hash
        self.judge_threshold = judge_threshold

    def _tool_calls(self) -> List[Any]:
        calls = (
            self.trace.get("tool_calls")
            or self.trace.get("tool_trace")
            or self.trace.get("tools")
            or []
        )
        if isinstance(calls, int):
            return list(range(calls))
        return list(calls)

    @staticmethod
    def _artifact_name(artifact: Any) -> str:
        """Extract a comparable file name from a flat string or structured entry."""
        if isinstance(artifact, dict):
            for key in ("path", "name", "file", "filename", "artifact"):
                value = artifact.get(key)
                if value:
                    return str(value)
            return str(artifact)
        return str(artifact)

    def _artifacts(self) -> List[str]:
        artifacts = (
            self.trace.get("artifacts")
            or self.trace.get("files")
            or self.trace.get("outputs")
            or []
        )
        if isinstance(artifacts, dict):
            artifacts = list(artifacts.values())
        return [self._artifact_name(a) for a in artifacts]

    def run(self, print_summary: bool = False, **kwargs) -> HarnessResult:
        """Evaluate the harness trace synchronously.

        Returns:
            HarnessResult with per-metric pass/fail and an overall score.
        """
        self.before_run()

        tool_calls = self._tool_calls()
        artifacts = self._artifacts()
        artifact_set = set(artifacts)

        tool_call_count = len(tool_calls)
        schema_hash = _schema_hash(self.trace.get("tool_schema"))

        missing_artifacts = [a for a in self.required_artifacts if a not in artifact_set]
        artifacts_complete = len(missing_artifacts) == 0

        tool_gate_passed = tool_call_count >= self.min_tool_calls

        if self.expected_schema_hash is None:
            schema_consistent = True
        else:
            schema_consistent = schema_hash == self.expected_schema_hash

        raw_judge_score = self.trace.get("judge_score")
        judge_score: Optional[float] = None
        if raw_judge_score is None:
            judge_passed = True  # No judge configured -> not a gate
        else:
            try:
                judge_score = float(raw_judge_score)
                judge_passed = judge_score >= self.judge_threshold
            except (TypeError, ValueError):
                # A malformed judge value must fail the gate, not crash the suite.
                judge_score = None
                judge_passed = False

        gates = [artifacts_complete, tool_gate_passed, schema_consistent, judge_passed]
        passed = all(gates)
        score = sum(1 for g in gates if g) / len(gates)

        result = HarnessResult(
            eval_id=self.eval_id,
            name=self.name,
            passed=passed,
            score=score,
            tool_call_count=tool_call_count,
            tool_calls_sufficient=tool_gate_passed,
            schema_hash=schema_hash,
            schema_consistent=schema_consistent,
            artifacts_complete=artifacts_complete,
            missing_artifacts=missing_artifacts,
            judge_score=judge_score,
            judge_passed=judge_passed,
            metadata={"required_artifacts": self.required_artifacts},
        )

        self._result = result
        self.after_run(result)

        if print_summary:
            result.print_summary()

        return result

    def to_eval_result(self, case_name: Optional[str] = None) -> "Any":
        """Convert the latest run into an ``EvalResult`` for ``EvalReport`` export."""
        from .package import EvalResult

        if self._result is None:
            self.run()

        r: HarnessResult = self._result
        return EvalResult(
            case_name=case_name or self.name,
            passed=r.passed,
            score=r.score,
            actual_output=None,
            error=None,
            criteria_scores={
                "artifacts_complete": 1.0 if r.artifacts_complete else 0.0,
                "tool_calls_sufficient": 1.0 if r.tool_calls_sufficient else 0.0,
                "schema_consistent": 1.0 if r.schema_consistent else 0.0,
                "judge_passed": 1.0 if r.judge_passed else 0.0,
            },
        )
