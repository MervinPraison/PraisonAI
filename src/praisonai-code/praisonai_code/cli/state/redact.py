"""Transcript redaction for safe session sharing (Issue #3426).

``praisonai session export`` produces a verbatim transcript. When a developer
wants to share a session — for a bug report, a repro, or an audit trail — a raw
export leaks secrets, absolute file paths, the working directory, and file
contents embedded in tool I/O. This module provides an opt-in, deterministic
redactor invoked only when ``--sanitise`` is passed; the default export is
left byte-for-byte unchanged.

Design (deliberately lightweight — stdlib only, no new dependencies):

* ``redact_transcript(payload, level="standard")`` walks the resolved
  ``{session_id, ..., chat_history, metadata}`` payload and replaces sensitive
  spans with *stable* opaque placeholders (``[redacted:secret:<n>]``,
  ``[redacted:path:<n>]``), so the same underlying value maps to the same
  placeholder within one export — preserving the readability of the flow.
* Order matters: process-registered secrets first (most sensitive), then any
  detected key/token patterns, then absolute paths and the cwd, so a path that
  is part of a secret is not half-masked.
* ``level="standard"`` redacts secrets and paths in every string. ``strict``
  is identical here — message text is already covered because we redact every
  string value in the payload — but the extra level is kept as an explicit,
  documented knob for callers that want the distinction to be visible.
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["redact_transcript"]

# Token/secret shapes worth masking even when never registered as a resolved
# secret. Kept intentionally small and high-signal to avoid over-redaction.
_SECRET_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),           # OpenAI-style keys
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),    # Slack tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),      # GitHub tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),                # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),          # Google API key
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{12,})"),
)

# Absolute POSIX or Windows paths. Matched last so secrets embedded in a path
# are already masked; short single-segment roots are ignored to limit noise.
_PATH_PATTERN = re.compile(r"(?:/[^\s\"'`:]+){2,}|[A-Za-z]:\\[^\s\"'`]+")


class _PlaceholderMap:
    """Assigns stable, monotonic placeholders per redaction category.

    The same source value always maps to the same placeholder for the life of
    one redaction pass, so a reader can still follow which value recurs where
    without ever seeing the value itself.
    """

    def __init__(self) -> None:
        self._maps: Dict[str, Dict[str, str]] = {}

    def get(self, category: str, value: str) -> str:
        bucket = self._maps.setdefault(category, {})
        if value not in bucket:
            bucket[value] = f"[redacted:{category}:{len(bucket) + 1}]"
        return bucket[value]


def _collect_registered_secrets() -> List[str]:
    """Return process-registered secret values, longest first (best-effort)."""
    try:
        from praisonaiagents.secrets import _redaction_values, _redaction_lock

        with _redaction_lock:
            values = [v for v in _redaction_values if isinstance(v, str) and v]
    except Exception:
        return []
    return sorted(values, key=len, reverse=True)


def _redact_string(text: str, mapper: _PlaceholderMap, secrets: List[str]) -> str:
    if not text or not isinstance(text, str):
        return text

    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, mapper.get("secret", secret))

    def _sub_secret(match: re.Match) -> str:
        return mapper.get("secret", match.group(0))

    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_sub_secret, text)

    def _sub_path(match: re.Match) -> str:
        return mapper.get("path", match.group(0))

    text = _PATH_PATTERN.sub(_sub_path, text)
    return text


def _redact_value(value: Any, mapper: _PlaceholderMap, secrets: List[str]) -> Any:
    if isinstance(value, str):
        return _redact_string(value, mapper, secrets)
    if isinstance(value, dict):
        return {k: _redact_value(v, mapper, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v, mapper, secrets) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v, mapper, secrets) for v in value)
    return value


def redact_transcript(
    payload: Dict[str, Any],
    level: str = "standard",
    extra_secrets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return a redacted copy of a resolved session ``payload``.

    Replaces detected secrets, absolute paths, and the current working
    directory with stable ``[redacted:<category>:<n>]`` placeholders across
    every string in the ``{info, messages, parts}`` structure (here the
    resolved ``chat_history``/``metadata`` view). The input is never mutated.

    Args:
        payload: The resolved session dict (as produced by ``to_dict()``).
        level: ``"standard"`` or ``"strict"``. Both mask secrets and paths in
            every string; ``strict`` is accepted for explicit intent.
        extra_secrets: Additional literal values to mask (e.g. seeded in tests).
    """
    if not isinstance(payload, dict):
        return payload

    mapper = _PlaceholderMap()
    secrets = list(extra_secrets or []) + _collect_registered_secrets()

    # Mask the workspace/cwd explicitly so a relative-looking cwd is caught even
    # when the path regex would skip a short single segment.
    try:
        cwd = os.getcwd()
        if cwd and len(cwd) > 1:
            secrets = secrets + [cwd]
    except Exception:
        pass

    # De-dupe while preserving longest-first ordering so a value that is a
    # substring of another is masked as the longer match first.
    seen: set = set()
    ordered: List[str] = []
    for s in sorted(secrets, key=len, reverse=True):
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)

    redacted = copy.deepcopy(payload)
    return _redact_value(redacted, mapper, ordered)
