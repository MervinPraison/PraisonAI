"""
Agent-authored reply contract for interactive bot UI.

Defines the seam that lets an agent (or a hook) emit a portable
``MessagePresentation`` as part of a normal reply, alongside optional text.
Channels render the presentation via the existing per-platform renderers and
fall back to text where rich UI is unsupported.

This is a core protocol with no heavy implementations: channel rendering and
session wiring live in the wrapper (praisonai). Producers return one of:

* ``str``                     -> plain text (unchanged, fully backward compatible)
* ``MessagePresentation``     -> interactive UI (text fallback derived from text blocks)
* ``AgentReply``              -> explicit text + presentation pairing
* a dict ``{"text": ..., "presentation": ...}`` -> serialised form

``extract_presentation`` normalises any of these into ``(text, presentation)``
so the bot session can stay agnostic about which form the agent used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from .presentation import MessagePresentation, BlockType


@dataclass
class AgentReply:
    """An agent reply that may carry interactive UI alongside text.

    Attributes:
        text: Plain-text answer (used as the text fallback for channels that
            cannot render rich UI, and as the spoken/preview content otherwise).
        presentation: Optional portable presentation with buttons/selects.
    """

    text: str = ""
    presentation: Optional[MessagePresentation] = None

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        data: dict = {"text": self.text}
        if self.presentation is not None:
            data["presentation"] = self.presentation.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AgentReply":
        """Create from a plain dict."""
        pres = data.get("presentation")
        return cls(
            text=data.get("text", "") or "",
            presentation=(
                MessagePresentation.from_dict(pres)
                if isinstance(pres, dict)
                else pres
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
