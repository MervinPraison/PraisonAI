"""Trials engine: K isolated attempts per case, unified scoring, pass-rate + frontier.

This is the missing runner behind :class:`~praisonaiagents.eval.package.EvalRunnerProtocol`.
It answers "does my agent actually work?" with statistics instead of one sampled run:
each :class:`EvalCase` is attempted ``k`` independent times, every completed attempt is
scored through a single :class:`TrialScore` contract, and the report gives per-case
pass rates plus the *frontier* band (cases with 0 < pass_rate < 1) where an agent is
capable-but-inconsistent.

Design (lightweight): stdlib only (asyncio, copy, json, time). Reuses the existing
``Judge`` and the tool-assertion logic (``ReliabilityEvaluator._extract_tool_calls``).
No new heavy dependencies, no new trace subsystem.

Example:
    from praisonaiagents.eval import EvalPackage, EvalCase, run_trials

    package = EvalPackage(name="checkout", cases=[
        EvalCase(name="refund", input="...", expected="...", verify=my_metric_fn),
        EvalCase(name="lookup", input="...", criteria=["cites the order id"]),
    ])
    report = run_trials(agent, package, k=8, concurrency=4)
    print(report.pass_rates())   # {"refund": 0.75, "lookup": 1.0}
    print(report.frontier())     # ["refund"]
    report.save("trials.json")
"""

import asyncio
import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from praisonaiagents._logging import get_logger

from .package import EvalCase, EvalPackage, EvalResult

logger = get_logger(__name__)


@dataclass
class TrialScore:
    """Unified per-attempt scoring contract.

    Attributes:
        value: Numeric score in [0, 1].
        passed: Whether the attempt is a pass.
        reason: Optional human-readable explanation.
    """
    value: float
    passed: bool
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "passed": self.passed, "reason": self.reason}


def _coerce_score(raw: Any, *, threshold: float = 0.5) -> TrialScore:
    """Normalise a ``verify`` return value (bool | float | TrialScore) to TrialScore."""
    if isinstance(raw, TrialScore):
        return raw
    if isinstance(raw, bool):
        return TrialScore(value=1.0 if raw else 0.0, passed=raw)
    if isinstance(raw, (int, float)):
        value = float(raw)
        return TrialScore(value=value, passed=value >= threshold)
    # Truthiness fallback for anything else.
    passed = bool(raw)
    return TrialScore(value=1.0 if passed else 0.0, passed=passed)


@dataclass
class TrialAttempt:
    """One isolated attempt at a case."""
    case_name: str
    attempt: int
    stop_reason: str  # "completed" | "error" | "timeout"
    output: Optional[str] = None
    score: Optional[TrialScore] = None
    duration_ms: float = 0.0
    record: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_name": self.case_name,
            "attempt": self.attempt,
            "stop_reason": self.stop_reason,
            "output": self.output,
            "score": self.score.to_dict() if self.score else None,
            "duration_ms": self.duration_ms,
            "record": self.record,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrialAttempt":
        score_data = data.get("score")
        score = TrialScore(**score_data) if score_data else None
        return cls(
            case_name=data["case_name"],
            attempt=data["attempt"],
            stop_reason=data["stop_reason"],
            output=data.get("output"),
            score=score,
            duration_ms=data.get("duration_ms", 0.0),
            record=data.get("record"),
        )

    def to_eval_result(self) -> EvalResult:
        """Adapt to the existing ``EvalResult`` shape (single-attempt view)."""
        return EvalResult(
            case_name=self.case_name,
            passed=bool(self.score and self.score.passed),
            score=float(self.score.value) if self.score else 0.0,
            actual_output=self.output,
            error=None if self.stop_reason == "completed" else self.stop_reason,
            latency_ms=self.duration_ms,
            record=self.record,
        )


@dataclass
class TrialReport:
    """Aggregated report from a trials run: cases -> attempts, with pass rates."""
    package_name: str
    k: int
    attempts: Dict[str, List[TrialAttempt]] = field(default_factory=dict)

    def _scored(self, case: str) -> List[TrialAttempt]:
        return [a for a in self.attempts.get(case, []) if a.score is not None]

    def pass_rates(self) -> Dict[str, float]:
        """Per-case pass rate over *scored* attempts (unscored excluded)."""
        rates: Dict[str, float] = {}
        for case in self.attempts:
            scored = self._scored(case)
            if not scored:
                rates[case] = 0.0
                continue
            passed = sum(1 for a in scored if a.score.passed)
            rates[case] = passed / len(scored)
        return rates

    def frontier(self) -> List[str]:
        """Cases with pass rate strictly between 0 and 1 (capable-but-inconsistent)."""
        return [c for c, r in self.pass_rates().items() if 0.0 < r < 1.0]

    def summary(self) -> Dict[str, Any]:
        """Stable dict for CI gating."""
        rates = self.pass_rates()
        per_case: Dict[str, Any] = {}
        for case in self.attempts:
            scored = self._scored(case)
            n_passed = sum(1 for a in scored if a.score.passed)
            mean_value = (
                sum(a.score.value for a in scored) / len(scored) if scored else 0.0
            )
            per_case[case] = {
                "n_attempts": len(self.attempts[case]),
                "n_scored": len(scored),
                "n_passed": n_passed,
                "pass_rate": rates[case],
                "mean_value": mean_value,
            }
        total_scored = sum(len(self._scored(c)) for c in self.attempts)
        total_passed = sum(
            1 for c in self.attempts for a in self._scored(c) if a.score.passed
        )
        return {
            "package_name": self.package_name,
            "k": self.k,
            "n_cases": len(self.attempts),
            "total_scored": total_scored,
            "total_passed": total_passed,
            "overall_pass_rate": (total_passed / total_scored) if total_scored else 0.0,
            "frontier": self.frontier(),
            "cases": per_case,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "k": self.k,
            "attempts": {
                case: [a.to_dict() for a in attempts]
                for case, attempts in self.attempts.items()
            },
            "summary": self.summary(),
        }

    def save(self, path: str) -> None:
        """Persist full attempt records (including trajectory) as JSON."""
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    def load(cls, path: str) -> "TrialReport":
        from pathlib import Path
        data = json.loads(Path(path).read_text())
        attempts = {
            case: [TrialAttempt.from_dict(a) for a in rows]
            for case, rows in data.get("attempts", {}).items()
        }
        return cls(
            package_name=data["package_name"],
            k=data.get("k", 1),
            attempts=attempts,
        )


def _isolated_agent_copy(agent: Any) -> Any:
    """Return a best-effort isolated copy of the agent for one attempt.

    Each attempt should be an independent sample: fresh session/chat history,
    caches cleared, and memory/knowledge *writes* severed so the caller's stores
    are never mutated. Falls back to the original agent when copy is unsupported.
    """
    try:
        clone = copy.copy(agent)
    except Exception:
        logger.debug("Agent copy failed; running attempts on the original agent")
        return agent

    # Fresh identity / session so attempts never share state.
    if hasattr(clone, "agent_id"):
        try:
            clone.agent_id = str(uuid.uuid4())
        except Exception:
            pass
    if hasattr(clone, "_session_id"):
        try:
            clone._session_id = str(uuid.uuid4())
        except Exception:
            pass

    # Independent chat history: rebind to a *new* list so appends during the
    # attempt never mutate the caller's shared list (a shallow copy shares it).
    try:
        clone.chat_history = list(getattr(agent, "chat_history", None) or [])
    except Exception:
        pass

    # Give the clone its own cache object rather than clearing the shared one,
    # so wiping per-attempt state cannot evict the original agent's cache.
    cache = getattr(clone, "_system_prompt_cache", None)
    if cache is not None:
        try:
            clone._system_prompt_cache = {}
        except Exception:
            pass

    # Sever memory/knowledge writes for the attempt (measurement must not mutate stores).
    for attr in ("memory", "knowledge"):
        if getattr(clone, attr, None) is not None:
            try:
                setattr(clone, attr, None)
            except Exception:
                pass

    return clone


def _extract_output(response: Any) -> str:
    return "" if response is None else str(response)


def _extract_tool_calls(agent: Any, response: Any) -> List[str]:
    """Reuse ReliabilityEvaluator's extraction logic for the attempt trajectory."""
    try:
        from .reliability import ReliabilityEvaluator
        evaluator = ReliabilityEvaluator(agent=agent, input_text="")
        return sorted(evaluator._extract_tool_calls(response))
    except Exception:
        return []


def _run_agent_once(agent: Any, input_text: str) -> Any:
    if hasattr(agent, "chat"):
        return agent.chat(input_text)
    if hasattr(agent, "start"):
        return agent.start(input_text)
    raise ValueError("Agent must have a 'chat' or 'start' method")


def _score_attempt(case: EvalCase, output: str, agent: Any, response: Any) -> TrialScore:
    """Resolve the single scorer contract for a completed attempt.

    Resolution order: ``verify`` callable -> tool assertions (metadata
    ``expected_tools``) -> ``criteria``/Judge. Runs only on completed attempts.
    """
    # 1. Explicit verify callable. A raising verifier is recorded as a failed
    # score (data), never propagated — one bad metric must not abort the report.
    if case.verify is not None:
        try:
            return _coerce_score(case.verify(output, case.expected))
        except Exception as e:
            logger.warning("verify() raised for case %r: %s", case.name, e)
            return TrialScore(value=0.0, passed=False, reason=f"verify error: {e}")

    # 2. Tool assertions from metadata (deterministic).
    expected_tools = case.metadata.get("expected_tools") if case.metadata else None
    if expected_tools:
        actual = set(_extract_tool_calls(agent, response))
        missing = [t for t in expected_tools if t not in actual]
        passed = not missing
        value = 1.0 - (len(missing) / len(expected_tools))
        reason = "all expected tools called" if passed else f"missing tools: {missing}"
        return TrialScore(value=value, passed=passed, reason=reason)

    # 3. Criteria / expected via the existing Judge.
    if case.criteria or case.expected is not None:
        try:
            from .judge import Judge
            criteria = ", ".join(case.criteria) if case.criteria else None
            result = Judge().run(
                output=output,
                expected=case.expected,
                criteria=criteria,
                input=case.input,
            )
            value = max(0.0, min(1.0, float(result.score) / 10.0))
            return TrialScore(value=value, passed=bool(result.passed), reason=result.reasoning)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Judge scoring failed for case %r: %s", case.name, e)
            return TrialScore(value=0.0, passed=False, reason=f"judge error: {e}")

    # Nothing to score against: treat a non-empty completion as a pass.
    passed = bool(output)
    return TrialScore(value=1.0 if passed else 0.0, passed=passed, reason="no scorer configured")


async def _run_single_attempt(
    agent: Any,
    case: EvalCase,
    attempt_index: int,
    *,
    capture_record: bool,
    executor: Any = None,
) -> TrialAttempt:
    """Run one isolated attempt; failures are recorded as data, never raised.

    Note on ``timeout``: the attempt runs in a worker thread via
    :func:`asyncio.to_thread`. On timeout the *awaiting* coroutine returns
    immediately with ``stop_reason="timeout"``, but Python cannot forcibly kill
    the underlying thread, so a wedged agent call may keep running in the
    background until it finishes on its own. The timeout bounds when the report
    is produced, not necessarily when every side effect stops.
    """
    start = time.perf_counter()
    isolated = _isolated_agent_copy(agent)
    loop = asyncio.get_running_loop()
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(executor, _run_agent_once, isolated, case.input),
            timeout=case.timeout_seconds,
        )
    except asyncio.TimeoutError:
        duration = (time.perf_counter() - start) * 1000.0
        return TrialAttempt(
            case_name=case.name, attempt=attempt_index,
            stop_reason="timeout", duration_ms=duration,
        )
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000.0
        logger.debug("Attempt %d of %r errored: %s", attempt_index, case.name, e)
        return TrialAttempt(
            case_name=case.name, attempt=attempt_index,
            stop_reason="error", duration_ms=duration,
            record={"error": str(e)} if capture_record else None,
        )

    duration = (time.perf_counter() - start) * 1000.0
    output = _extract_output(response)
    try:
        score = _score_attempt(case, output, isolated, response)
    except Exception as e:  # pragma: no cover - defensive last resort
        logger.warning("Scoring failed for case %r: %s", case.name, e)
        score = TrialScore(value=0.0, passed=False, reason=f"scoring error: {e}")

    record = None
    if capture_record:
        record = {
            "input": case.input,
            "output": output,
            "tool_calls": _extract_tool_calls(isolated, response),
        }

    return TrialAttempt(
        case_name=case.name,
        attempt=attempt_index,
        stop_reason="completed",
        output=output,
        score=score,
        duration_ms=duration,
        record=record,
    )


async def arun_trials(
    agent: Any,
    package: EvalPackage,
    *,
    k: int = 1,
    concurrency: int = 1,
    capture_record: bool = True,
) -> TrialReport:
    """Async: run ``k`` isolated attempts per case with bounded concurrency.

    Args:
        agent: The agent under test (needs ``chat`` or ``start``).
        package: The :class:`EvalPackage` of cases.
        k: Independent attempts per case.
        concurrency: Max attempts running concurrently (semaphore-bounded).
        capture_record: Store the per-attempt trajectory (input/output/tool_calls).

    Returns:
        A :class:`TrialReport` with deterministic attempt ordering.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    semaphore = asyncio.Semaphore(max(1, concurrency))

    # Dedicated executor sized to the concurrency budget. It is *not* joined on
    # exit: a timed-out worker thread cannot be killed, and blocking on it would
    # defeat the per-case timeout. Abandoning it lets ``arun_trials`` return
    # promptly while the OS reclaims the leaked thread when it eventually ends.
    import concurrent.futures

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, concurrency)
    )

    async def _bounded(case: EvalCase, idx: int) -> TrialAttempt:
        async with semaphore:
            return await _run_single_attempt(
                agent, case, idx, capture_record=capture_record, executor=executor
            )

    report = TrialReport(package_name=package.name, k=k)
    try:
        for case in package.cases:
            tasks = [_bounded(case, i) for i in range(k)]
            results = await asyncio.gather(*tasks)
            # Stable, deterministic assembly order by attempt index.
            results = sorted(results, key=lambda a: a.attempt)
            # Cases can legitimately share a name (e.g. same case re-run):
            # append instead of overwriting so no attempts are silently dropped.
            existing = report.attempts.setdefault(case.name, [])
            offset = len(existing)
            for r in results:
                r.attempt += offset
            existing.extend(results)
    finally:
        # Do not wait for potentially-wedged workers (see note above).
        executor.shutdown(wait=False)
    return report


def run_trials(
    agent: Any,
    package: EvalPackage,
    *,
    k: int = 1,
    concurrency: int = 1,
    capture_record: bool = True,
) -> TrialReport:
    """Sync wrapper around :func:`arun_trials` (see it for arguments)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            arun_trials(agent, package, k=k, concurrency=concurrency,
                        capture_record=capture_record)
        )
    # Already inside an event loop: run on a dedicated loop in a worker thread.
    import concurrent.futures

    def _runner() -> TrialReport:
        return asyncio.run(
            arun_trials(agent, package, k=k, concurrency=concurrency,
                        capture_record=capture_record)
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result()
