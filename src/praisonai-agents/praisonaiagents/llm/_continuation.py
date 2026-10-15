"""Bounded auto-continuation for responses cut off by the output-token limit.

When a final (no tool calls) assistant message stops with
``finish_reason == "length"``, the turn loop re-prompts the model to continue
and stitches the pieces into one message, up to a small cap. Past the cap the
existing ``length_truncated`` outcome is surfaced unchanged.
"""

from typing import Any, Dict, List, Optional

CONTINUE_PROMPT = (
    "Your previous response was cut off by the output token limit. "
    "Continue exactly where you left off. Do not repeat anything you already "
    "wrote and do not add any preamble."
)

DEFAULT_MAX_CONTINUATIONS = 3


class OutputContinuation:
    """Per-turn continuation state. ``setting``: True/None=default cap, False/0=off, int=cap."""

    __slots__ = ("remaining", "text")

    def __init__(self, setting: Any = True) -> None:
        if setting is None or setting is True:
            self.remaining = DEFAULT_MAX_CONTINUATIONS
        elif setting is False:
            self.remaining = 0
        else:
            self.remaining = max(0, int(setting))
        self.text = ""

    def take(self, messages: List[Dict[str, Any]], partial: Optional[str], truncated: bool) -> bool:
        """Queue a continuation request for a length-truncated ``partial``.

        Appends the partial assistant turn plus a continue prompt to
        ``messages`` and returns True, or returns False (no-op) when not
        truncated, empty, or the cap is exhausted.
        """
        if not truncated or not partial or self.remaining <= 0:
            return False
        self.remaining -= 1
        self.text += partial
        messages.append({"role": "assistant", "content": partial})
        messages.append({"role": "user", "content": CONTINUE_PROMPT})
        return True

    def stitch(self, text: Optional[str]) -> Optional[str]:
        """Prefix earlier truncated pieces onto the final ``text``."""
        if not self.text:
            return text
        return self.text + (text or "")


def is_structured(response_format: Any) -> bool:
    """True when ``response_format`` enforces JSON/schema output (stitching would break it)."""
    if isinstance(response_format, dict):
        return response_format.get("type", "text") != "text"
    return bool(response_format)
