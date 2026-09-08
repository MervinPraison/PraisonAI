"""Load eval cases from JSONL, and export passing runs as training data.

``EvalCase.from_dict`` existed but nothing read a FILE, so a task set had to be
assembled in Python. And ``praisonai-train`` sat in the repo with no connection
to ``eval``: there was no way to take the runs that scored well and turn them
into supervised fine-tuning data, which is the obvious next step after
measuring.

    cases = load_cases("tasks.jsonl")
    report = suite.run(cases)
    export_sft(report, "train.jsonl", min_score=0.8)

JSONL rather than a new format: it is what Agno, OpenAI's fine-tuning API and
every dataset tool already speak, so a task set is portable in and the training
file is portable out.
"""

import json
import os
from typing import Any, Dict, Iterable, Iterator, List, Optional

__all__ = [
    "DatasetError",
    "load_cases",
    "iter_jsonl",
    "export_sft",
    "sft_records",
]


class DatasetError(ValueError):
    """Raised when a dataset file cannot be read or written."""


def iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    """Yield one dict per line, reporting WHICH line failed.

    A malformed line is named by number rather than collapsing the file into a
    generic parse error -- with a thousand-line dataset, "invalid JSON" is not
    an actionable message.
    """
    if not os.path.exists(path):
        raise DatasetError(f"No such dataset file: {path!r}")
    with open(path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text or text.startswith("//"):
                continue
            try:
                row = json.loads(text)
            except ValueError as exc:
                raise DatasetError(f"{path}:{number}: not valid JSON -- {exc}") from exc
            if not isinstance(row, dict):
                raise DatasetError(
                    f"{path}:{number}: each line must be a JSON object, got {type(row).__name__}"
                )
            yield row


def load_cases(path: str, *, case_cls: Optional[type] = None) -> List[Any]:
    """Read a JSONL task set into EvalCase objects."""
    if case_cls is None:
        from .package import EvalCase as case_cls  # type: ignore

    cases: List[Any] = []
    for number, row in enumerate(iter_jsonl(path), start=1):
        # Accept the common aliases rather than demanding one spelling: a task
        # set exported from another tool is the normal case, not the exception.
        data = dict(row)
        if "input" not in data:
            for alias in ("prompt", "question", "query", "instruction"):
                if alias in data:
                    data["input"] = data.pop(alias)
                    break
        if "expected" not in data:
            for alias in ("expected_output", "answer", "output", "completion"):
                if alias in data:
                    data["expected"] = data.pop(alias)
                    break
        data.setdefault("name", f"case_{number}")

        known = {"name", "input", "expected", "criteria", "metadata", "timeout_seconds"}
        extra = {k: v for k, v in data.items() if k not in known}
        kwargs = {k: v for k, v in data.items() if k in known}
        if extra:
            # Keep unrecognised columns instead of dropping them: a dataset
            # usually carries provenance (source, difficulty, id) that is worth
            # having in the report.
            kwargs["metadata"] = {**(kwargs.get("metadata") or {}), **extra}
        try:
            cases.append(case_cls(**kwargs))
        except Exception as exc:
            raise DatasetError(f"{path}:{number}: {type(exc).__name__}: {exc}") from exc
    if not cases:
        raise DatasetError(
            f"{path!r} contained no cases. An empty task set would report a "
            f"perfect pass rate over nothing."
        )
    return cases


def sft_records(
    report: Any,
    *,
    min_score: float = 1.0,
    system_prompt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Turn the runs that scored well into chat-format training records.

    Only PASSING runs at or above ``min_score`` are exported. Training on a run
    the evaluation rejected would teach the model the behaviour the eval exists
    to catch.
    """
    results = getattr(report, "results", None)
    if results is None:
        results = report if isinstance(report, (list, tuple)) else None
    if results is None:
        raise DatasetError(
            "Expected an EvalReport (or a list of EvalResult); got "
            f"{type(report).__name__}."
        )

    records: List[Dict[str, Any]] = []
    for result in results:
        if not getattr(result, "passed", False):
            continue
        if float(getattr(result, "score", 0.0)) < min_score:
            continue
        prompt = (getattr(result, "record", None) or {}).get("input")
        completion = getattr(result, "actual_output", None)
        if not prompt or not completion:
            # Without both halves there is nothing to learn from; skipping
            # silently would quietly shrink the training set.
            continue
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages += [
            {"role": "user", "content": str(prompt)},
            {"role": "assistant", "content": str(completion)},
        ]
        records.append({"messages": messages})
    return records


def export_sft(
    report: Any,
    path: str,
    *,
    min_score: float = 1.0,
    system_prompt: Optional[str] = None,
) -> int:
    """Write passing runs to ``path`` as JSONL. Returns how many were written."""
    records = sft_records(report, min_score=min_score, system_prompt=system_prompt)
    if not records:
        raise DatasetError(
            f"No run scored >= {min_score} with both a prompt and an output, so "
            f"there is nothing to train on. Writing an empty file would look "
            f"like a successful export."
        )
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return len(records)
