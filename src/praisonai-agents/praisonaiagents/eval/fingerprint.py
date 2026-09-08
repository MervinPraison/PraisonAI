"""A fingerprint for the setup an evaluation ran under.

Scores are only comparable when the thing being scored did not change. Nothing
stopped today's numbers being compared against a run made with a different
model, a different prompt, or a different tool set -- and that comparison looks
perfectly normal, which is what makes it dangerous: the graph moves and the
cause is invisible.

A fingerprint hashes the parts of a setup that change what a score MEANS, so
two runs can be checked before their numbers are put side by side.

    fp = run_fingerprint(model="gpt-4o", prompt=agent.instructions, tools=agent.tools)
    ...
    assert_comparable(previous.fingerprint, fp)   # raises if the setup moved

Deliberately NOT included: anything that varies run to run without changing
meaning (timestamps, run ids, sample order, latency). A fingerprint that
changes every run would refuse every comparison and be switched off.
"""

import hashlib
import json
from typing import Any, Iterable, Optional

__all__ = [
    "FINGERPRINT_VERSION",
    "run_fingerprint",
    "fingerprint_parts",
    "compare_fingerprints",
    "assert_comparable",
    "FingerprintMismatch",
]

#: Bump when the INPUTS change, so old fingerprints are never silently treated
#: as comparable to new ones computed from a different recipe.
FINGERPRINT_VERSION = "evalfp1"


class FingerprintMismatch(ValueError):
    """Raised when two evaluation runs are not comparable."""

    def __init__(self, left: str, right: str, differing: Optional[list] = None):
        detail = f" Differing: {', '.join(differing)}." if differing else ""
        super().__init__(
            f"These evaluation runs are not comparable: {left} != {right}.{detail} "
            f"Scores from different setups cannot be put side by side. Re-run the "
            f"baseline under the current setup, or compare against a run with the "
            f"same fingerprint."
        )
        self.left = left
        self.right = right
        self.differing = differing or []


def _tool_names(tools: Any) -> list:
    """Tool identity, order-independent: a reordered tool list is the same setup."""
    if not tools:
        return []
    names = []
    for tool in tools if isinstance(tools, (list, tuple, set)) else [tools]:
        name = (
            getattr(tool, "name", None)
            or getattr(tool, "__name__", None)
            or (tool if isinstance(tool, str) else type(tool).__name__)
        )
        names.append(str(name))
    return sorted(names)


def _prompt_shape(prompt: Any) -> str:
    """
    The prompt's IDENTITY, hashed rather than stored.

    The full text is not kept: a prompt can carry customer data, and a
    fingerprint is meant to be written to result files and shared.
    """
    if prompt is None:
        return ""
    text = prompt if isinstance(prompt, str) else json.dumps(prompt, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fingerprint_parts(
    model: Any = None,
    prompt: Any = None,
    tools: Any = None,
    evaluators: Optional[Iterable[str]] = None,
    extra: Optional[dict] = None,
) -> dict:
    """The exact inputs a fingerprint is computed from, for diagnosis."""
    model_id = getattr(model, "model", None) or getattr(model, "name", None) or model
    return {
        "version": FINGERPRINT_VERSION,
        "model": str(model_id) if model_id is not None else "",
        "prompt": _prompt_shape(prompt),
        "tools": _tool_names(tools),
        "evaluators": sorted(str(e) for e in (evaluators or [])),
        "extra": {k: str(v) for k, v in sorted((extra or {}).items())},
    }


def run_fingerprint(
    model: Any = None,
    prompt: Any = None,
    tools: Any = None,
    evaluators: Optional[Iterable[str]] = None,
    extra: Optional[dict] = None,
) -> str:
    """A short, stable id for this evaluation setup."""
    parts = fingerprint_parts(model, prompt, tools, evaluators, extra)
    blob = json.dumps(parts, sort_keys=True)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f"{FINGERPRINT_VERSION}:{digest}"


def compare_fingerprints(left: str, right: str) -> bool:
    """True when two runs were made under the same setup."""
    return bool(left) and bool(right) and left == right


def assert_comparable(left: str, right: str, differing: Optional[list] = None) -> None:
    """Raise unless two runs are comparable. Missing fingerprints are NOT assumed equal."""
    if not compare_fingerprints(left, right):
        raise FingerprintMismatch(left or "<none>", right or "<none>", differing)
