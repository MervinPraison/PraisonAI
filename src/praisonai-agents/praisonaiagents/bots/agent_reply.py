"""
Agent-authored reply contract for interactive bot UI.

Defines the seam that lets an agent (or a hook) emit a portable
``MessagePresentation`` as part of a normal reply, alongside optional text.
Channels render the presentation via the existing per-platform renderers and
fall back to text where rich UI is unsupported.

This is a core protocol with no heavy implementations: channel rendering and
session wiring live in ``praisonai-bot`` (``praisonai_bot.bots``). Producers return one of:

* ``str``                     -> plain text (unchanged, fully backward compatible)
* ``MessagePresentation``     -> interactive UI (text fallback derived from text blocks)
* ``AgentReply``              -> explicit text + presentation pairing
* a dict ``{"text": ..., "presentation": ...}`` -> serialised form

``extract_presentation`` normalises any of these into ``(text, presentation)``
so the bot session can stay agnostic about which form the agent used.

An ``AgentReply`` may also carry an optional ``completion`` (:class:`TurnCompletion`)
describing *why* the turn ended. ``extract_completion`` pulls it off any result
(including a bare ``Agent`` via its ``last_stop_reason``), and
``append_completion_note`` lets a gateway optionally surface a concise, user-safe
note (e.g. "stopped after reaching the step limit") when a turn stops early —
off by default, so clean completions and existing deployments are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .presentation import MessagePresentation, BlockType


# User-safe notes keyed by stop reason. ``completed`` is intentionally absent:
# a clean turn never surfaces a note. Reasons mirror ``Agent.last_stop_reason``
# (``completed | max_steps | cancelled | error``); unknown reasons degrade to a
# generic note so new runtime reasons stay forward-compatible.
_COMPLETION_NOTES = {
    "max_steps": "⏳ I stopped after reaching the step limit — reply "
    "\"continue\" to carry on.",
    "cancelled": "🛑 This turn was interrupted before it finished — send it "
    "again to retry.",
    "error": "⚠️ This turn ended early due to an error — please try again.",
}

# Reasons that represent a clean finish (no note surfaced).
_CLEAN_REASONS = frozenset({"completed", ""})


@dataclass
class TurnCompletion:
    """Why an agent turn ended, in a form the gateway can show the user.

    Wraps the coarse ``Agent.last_stop_reason`` string into a portable value
    the bot reply path can render. Off-band for ``completed`` (no note); for
    any early stop it yields a concise, localisable :meth:`note`.

    Attributes:
        reason: The stop reason string (``completed | max_steps | cancelled |
            error`` today; unknown values are tolerated).
        detail: Optional short, user-safe explanation overriding the default
            note for ``reason``.
    """

    reason: str = "completed"
    detail: str = ""

    @property
    def truncated(self) -> bool:
        """Whether the turn stopped before a clean completion."""
        return self.reason not in _CLEAN_REASONS

    def note(self) -> str:
        """A concise, user-facing note, or ``""`` for a clean completion."""
        if not self.truncated:
            return ""
        if self.detail:
            return self.detail
        return _COMPLETION_NOTES.get(
            self.reason,
            "⏳ This turn ended early — please try again.",
        )

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        data: dict = {"reason": self.reason}
        if self.detail:
            data["detail"] = self.detail
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TurnCompletion":
        """Create from a plain dict."""
        return cls(
            reason=data.get("reason", "completed") or "completed",
            detail=data.get("detail", "") or "",
        )


@dataclass
class AgentReply:
    """An agent reply that may carry interactive UI alongside text.

    Attributes:
        text: Plain-text answer (used as the text fallback for channels that
            cannot render rich UI, and as the spoken/preview content otherwise).
        presentation: Optional portable presentation with buttons/selects.
        completion: Optional reason the turn ended, so the gateway can surface a
            note when a turn stops early (defaults to ``None`` — unchanged for
            existing producers).
    """

    text: str = ""
    presentation: Optional[MessagePresentation] = None
    completion: Optional[TurnCompletion] = None

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        data: dict = {"text": self.text}
        if self.presentation is not None:
            data["presentation"] = self.presentation.to_dict()
        if self.completion is not None:
            data["completion"] = self.completion.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AgentReply":
        """Create from a plain dict."""
        pres = data.get("presentation")
        comp = data.get("completion")
        return cls(
            text=data.get("text", "") or "",
            presentation=(
                MessagePresentation.from_dict(pres)
                if isinstance(pres, dict)
                else pres
            ),
            completion=(
                TurnCompletion.from_dict(comp)
                if isinstance(comp, dict)
                else comp
            ),
        )


def _text_from_presentation(presentation: MessagePresentation) -> str:
    """Derive a plain-text fallback from a presentation's text/context blocks."""
    parts = []
    for block in presentation.blocks:
        btype = block.type.value if isinstance(block.type, BlockType) else block.type
        if btype in (BlockType.TEXT.value, BlockType.CONTEXT.value) and block.text:
            parts.append(block.text)
    return "\n\n".join(parts)


def extract_presentation(
    result: Any,
) -> Tuple[str, Optional[MessagePresentation]]:
    """Normalise an agent result into ``(text, presentation)``.

    Accepts the plain ``str`` reply path (returns ``(result, None)``), an
    ``AgentReply``, a ``MessagePresentation`` (text fallback derived from its
    text blocks), a serialised dict, or any object exposing a ``presentation``
    attribute. This keeps the bot session backward compatible: existing
    string-returning agents are unaffected, while presentation-aware agents get
    their UI rendered.

    Args:
        result: The value returned/emitted by an agent turn.

    Returns:
        A ``(text, presentation)`` tuple. ``presentation`` is ``None`` when the
        result carried no interactive UI.
    """
    if result is None:
        return ("", None)

    if isinstance(result, str):
        return (result, None)

    if isinstance(result, AgentReply):
        text = result.text
        if not text and result.presentation is not None:
            text = _text_from_presentation(result.presentation)
        return (text, result.presentation)

    if isinstance(result, MessagePresentation):
        return (_text_from_presentation(result), result)

    if isinstance(result, dict) and (
        "presentation" in result or "blocks" in result
    ):
        if "blocks" in result and "presentation" not in result:
            pres = MessagePresentation.from_dict(result)
            return (_text_from_presentation(pres), pres)
        reply = AgentReply.from_dict(result)
        text = reply.text
        if not text and reply.presentation is not None:
            text = _text_from_presentation(reply.presentation)
        return (text, reply.presentation)

    # Duck-typed: any object exposing a ``presentation`` attribute.
    pres = getattr(result, "presentation", None)
    if isinstance(pres, MessagePresentation):
        text = getattr(result, "text", None)
        if not text:
            text = getattr(result, "output", None) or _text_from_presentation(pres)
        return (str(text), pres)

    # Unknown shape: stringify so the text path stays robust.
    return (str(result), None)


def extract_completion(result: Any) -> Optional[TurnCompletion]:
    """Pull a :class:`TurnCompletion` off an agent result, if present.

    Recognises an ``AgentReply`` with a ``completion``, a serialised dict, or
    any object exposing a ``completion``/``last_stop_reason`` attribute (e.g. an
    ``Agent``). Returns ``None`` when no reason is available, so the bot session
    stays backward compatible with plain-text and presentation-only replies.
    """
    if result is None or isinstance(result, str):
        return None

    completion = getattr(result, "completion", None)
    if isinstance(completion, TurnCompletion):
        return completion

    if isinstance(result, dict):
        comp = result.get("completion")
        if isinstance(comp, TurnCompletion):
            return comp
        if isinstance(comp, dict):
            return TurnCompletion.from_dict(comp)
        return None

    reason = getattr(result, "last_stop_reason", None)
    if isinstance(reason, str) and reason:
        return TurnCompletion(reason=reason)
    return None


def append_completion_note(
    text: str, completion: Optional[TurnCompletion], *, enabled: bool = False
) -> str:
    """Append a completion note to ``text`` when a turn stopped early.

    Off by default: the gateway opts in (e.g. ``runtime.surface_completion_reason``)
    so ``completed`` turns and existing deployments are unchanged. Returns
    ``text`` untouched when disabled, when there is no completion, or when the
    turn completed cleanly.
    """
    if not enabled or completion is None:
        return text
    note = completion.note()
    if not note:
        return text
    return f"{text}\n\n{note}" if text else note
