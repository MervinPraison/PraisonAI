"""Export a trials report into a supervised fine-tuning (SFT) dataset.

Closes the loop from *verification* to *data generation*: take a trials report
(K scored attempts per case with captured trajectories), keep the attempts that
passed the verifier, and write them as a dataset the existing trainer consumes
directly — turning "run the agent K times, keep what passed, fine-tune on it,
re-run to measure gain" into a supported pipeline instead of a hand-rolled
script.

The report's *serialised JSON* is the contract with the (sibling) core trials
engine, so the loader is duck-typed over plain dicts: any report exposing
``package`` and ``cases`` (each with ``case_id`` and ``attempts``) works, whether
it comes from the core engine or an interim adapter.

Selection discipline (each skip is counted, never silent):

* attempts with ``score is None`` are never candidates (unscored → cannot judge);
* ``only_passed`` (default) keeps only verifier-passed attempts — this is
  rejection sampling: it amplifies existing behaviour and inherits any judge
  bias in the scorer;
* ``frontier_only`` (default) restricts to cases with ``0 < pass_rate < 1`` —
  saturated (all-pass) cases add K near-duplicates of mastered behaviour and
  zero-pass cases have nothing to export;
* tool-using runs are excluded by default (``skipped_tool_runs``): exporting only
  the final text of a run that used tools would train the model to answer
  *without* the tools it actually needed.

Output is one JSON object per line in ShareGPT shape
(``{"conversations": [{"role", "content"}, ...]}``) — exactly what the trainer's
``process_dataset`` standardises — or Alpaca (``instruction``/``input``/``output``)
via ``format="alpaca"``. A ``{path}.meta.json`` provenance sidecar maps every
emitted line back to the case id, attempt index and score that produced it, and
records the selection options, so any dataset row is traceable to its exact run.
Emission order is deterministic (case order, then attempt order) → reproducible
files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ExportSummary:
    """Counters returned by :func:`export_trials` — every attempt is accounted for."""

    written: int = 0
    skipped_unscored: int = 0
    skipped_failed: int = 0
    skipped_saturated: int = 0
    skipped_tool_runs: int = 0
    skipped_no_text: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    def __str__(self) -> str:  # concise, CLI-friendly
        return (
            f"written={self.written} "
            f"skipped_failed={self.skipped_failed} "
            f"skipped_tool_runs={self.skipped_tool_runs} "
            f"skipped_no_text={self.skipped_no_text} "
            f"skipped_unscored={self.skipped_unscored} "
            f"skipped_saturated={self.skipped_saturated}"
        )


@dataclass
class _Line:
    """One emitted dataset row plus the provenance needed to trace it."""

    row: dict[str, Any]
    case_id: str
    attempt_index: int
    score: Any


# ── report access (duck-typed over dict or object) ────────────────────────────

def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _load_report(report: Any) -> Any:
    """Accept a report object, a dict, or a path to a serialised JSON report."""
    if isinstance(report, (str, Path)):
        return json.loads(Path(report).read_text())
    return report


def _pass_threshold(attempt: Any) -> Optional[float]:
    """The verifier's passing cutoff for this attempt, if the report carries one.

    Looked up on the attempt (``pass_threshold`` / ``threshold`` / ``min_score``)
    so a score-only report can still be judged against the exact bar the verifier
    used, instead of the naive ``score > 0``.
    """
    for key in ("pass_threshold", "threshold", "min_score"):
        val = _get(attempt, key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _passed(attempt: Any) -> bool:
    """A verifier-passed attempt.

    Prefers an explicit ``passed`` flag. Otherwise compares the numeric score
    against the report's own passing threshold when one is present
    (``pass_threshold``/``threshold``/``min_score``); only when no threshold is
    carried does it fall back to treating a positive score as a pass, matching the
    "keep what passed" rejection-sampling contract for bare score-only reports.
    """
    passed = _get(attempt, "passed")
    if passed is not None:
        return bool(passed)
    score = _get(attempt, "score")
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return False
    threshold = _pass_threshold(attempt)
    if threshold is not None:
        return score_f >= threshold
    return score_f > 0


def _used_tools(attempt: Any) -> bool:
    tool_calls = _get(attempt, "tool_calls")
    if tool_calls:
        return True
    for msg in _get(attempt, "messages", []) or []:
        if _get(msg, "tool_calls") or _get(msg, "role") == "tool":
            return True
    return False


def _conversation_from(attempt: Any) -> Optional[list[dict[str, str]]]:
    """Build ShareGPT turns from an attempt's captured messages.

    History is excluded (only the attempt's own messages), the conversation is
    truncated at the final assistant message, and the assistant content is the
    raw generated text — never a re-serialisation of parsed output.
    """
    messages = _get(attempt, "messages")
    turns: list[dict[str, str]] = []
    if messages:
        for msg in messages:
            if _get(msg, "history"):
                continue
            role = _get(msg, "role")
            content = _get(msg, "content")
            if role is None or content is None:
                continue
            turns.append({"role": str(role), "content": str(content)})
        # Truncate at the final assistant message: drop any trailing non-assistant
        # turns so the row always ends on the target the model should learn.
        last_assistant = max(
            (i for i, t in enumerate(turns) if t["role"] == "assistant"),
            default=None,
        )
        if last_assistant is None:
            return None
        turns = turns[: last_assistant + 1]
        return turns

    # Fallback for reports that store input/output rather than messages.
    output = _get(attempt, "output")
    if output is None:
        return None
    user = _get(attempt, "input") or _get(attempt, "input_text")
    system = _get(attempt, "system")
    if system:
        turns.append({"role": "system", "content": str(system)})
    if user:
        turns.append({"role": "user", "content": str(user)})
    turns.append({"role": "assistant", "content": str(output)})
    return turns


def _to_alpaca(turns: list[dict[str, str]]) -> dict[str, str]:
    """Flatten ShareGPT turns to instruction/input/output (Alpaca)."""
    system = "".join(t["content"] for t in turns if t["role"] == "system")
    users = [t["content"] for t in turns if t["role"] == "user"]
    output = next(
        (t["content"] for t in reversed(turns) if t["role"] == "assistant"), ""
    )
    if system:
        # System text is the instruction; every user turn is the input so the
        # (often sole) user prompt is never dropped.
        instruction, input_users = system, users
    else:
        # No system: first user turn is the instruction, the rest is the input.
        instruction, input_users = (users[0] if users else ""), users[1:]
    return {
        "instruction": instruction,
        "input": "\n".join(input_users),
        "output": output,
    }


def _classify(attempt: Any, only_passed: bool, summary: ExportSummary):
    """Ordered filter; returns turns to emit or ``None`` (and bumps a counter)."""
    if _get(attempt, "score") is None:
        # Unscored can't be judged as passing, so they're only ever candidates
        # under ``--all`` (only_passed=False), which explicitly opts into them.
        if only_passed:
            summary.skipped_unscored += 1
            return None
    elif only_passed and not _passed(attempt):
        summary.skipped_failed += 1
        return None
    if _used_tools(attempt):
        summary.skipped_tool_runs += 1
        return None
    turns = _conversation_from(attempt)
    if not turns:
        summary.skipped_no_text += 1
        return None
    return turns


def _pass_rate(attempts: list[Any]) -> Optional[float]:
    scored = [a for a in attempts if _get(a, "score") is not None]
    if not scored:
        return None
    return sum(1 for a in scored if _passed(a)) / len(scored)


def export_trials(
    report: Any,
    path: str | Path,
    *,
    only_passed: bool = True,
    frontier_only: bool = True,
    format: str = "messages",
    qc: bool = False,
    qc_cfg: Optional[dict] = None,
) -> ExportSummary:
    """Export passing trial attempts to an SFT dataset JSONL + provenance sidecar.

    Args:
        report: a report object, a dict, or a path to serialised report JSON.
        path: destination ``.jsonl`` (a ``{path}.meta.json`` sidecar is written
            alongside).
        only_passed: keep only verifier-passed attempts (rejection sampling).
        frontier_only: keep only cases with ``0 < pass_rate < 1``.
        format: ``"messages"`` (ShareGPT ``conversations``) or ``"alpaca"``.
        qc: run emitted rows through ``data.qc.filter_rows`` before writing.
        qc_cfg: config forwarded to the QC filter.

    Returns:
        :class:`ExportSummary` with per-reason skip counters.
    """
    if format not in ("messages", "alpaca"):
        raise ValueError(f"format must be 'messages' or 'alpaca', got {format!r}")

    report = _load_report(report)
    summary = ExportSummary()
    lines: list[_Line] = []

    for case in _get(report, "cases", []) or []:
        attempts = list(_get(case, "attempts", []) or [])
        case_id = str(_get(case, "case_id", _get(case, "id", "")))
        if frontier_only:
            rate = _pass_rate(attempts)
            if rate is None or not (0.0 < rate < 1.0):
                summary.skipped_saturated += len(attempts)
                continue
        for idx, attempt in enumerate(attempts):
            turns = _classify(attempt, only_passed, summary)
            if turns is None:
                continue
            row = {"conversations": turns} if format == "messages" else _to_alpaca(turns)
            lines.append(
                _Line(row=row, case_id=case_id, attempt_index=idx,
                      score=_get(attempt, "score"))
            )

    if qc:
        kept_rows = filter_rows_for_export([ln.row for ln in lines], qc_cfg, format)
        kept_ids = {id(r) for r in kept_rows}
        lines = [ln for ln in lines if id(ln.row) in kept_ids]

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for ln in lines:
            fh.write(json.dumps(ln.row, ensure_ascii=False) + "\n")
    summary.written = len(lines)

    meta = {
        "package": _get(report, "package", _get(report, "package_name")),
        "source_report": _get(report, "source", _get(report, "report_id")),
        "options": {
            "only_passed": only_passed,
            "frontier_only": frontier_only,
            "format": format,
            "qc": qc,
        },
        "summary": summary.to_dict(),
        "lines": [
            {"case_id": ln.case_id, "attempt_index": ln.attempt_index, "score": ln.score}
            for ln in lines
        ],
    }
    Path(f"{out_path}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    return summary


def filter_rows_for_export(rows: list[dict], cfg: Optional[dict], format: str) -> list[dict]:
    """Run rows through the existing QC filter, adapting ShareGPT to its fields.

    ``data.qc`` operates on ``instruction``/``input``/``output`` rows, so ShareGPT
    rows are mapped to a QC view keyed back to the original row identity.
    """
    from praisonai_train.data.qc import filter_rows

    if format == "alpaca":
        kept = filter_rows(rows, cfg)
        kept_set = {id(r) for r in kept}
        return [r for r in rows if id(r) in kept_set]

    views: list[dict] = []
    view_to_row: dict[int, dict] = {}
    for r in rows:
        view = _to_alpaca(r["conversations"])
        views.append(view)
        view_to_row[id(view)] = r
    kept_views = filter_rows(views, cfg)
    kept_view_ids = {id(v) for v in kept_views}
    return [view_to_row[id(v)] for v in views if id(v) in kept_view_ids]
