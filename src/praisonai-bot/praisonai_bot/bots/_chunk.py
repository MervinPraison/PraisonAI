"""
Markdown-aware message chunking for PraisonAI bots.

Splits long bot responses at paragraph boundaries while preserving
code fences and markdown structure.  Inspired by OpenClaw's chunk.ts
but kept minimal (~120 lines).

Usage::

    from praisonai_bot.bots._chunk import chunk_message

    chunks = chunk_message(text, max_length=4096, preserve_fences=True)
    for chunk in chunks:
        await bot.send_message(channel_id, chunk)
"""

from __future__ import annotations

import re
from typing import List


def _calculate_length(text: str, unit: str = "codepoints") -> int:
    """Calculate text length based on the specified unit.
    
    Args:
        text: The text to measure
        unit: "codepoints" (default) or "utf16"
        
    Returns:
        Length of text in the specified unit
    """
    if unit == "utf16":
        # UTF-16 length (used by Telegram)
        return len(text.encode('utf-16-le')) // 2
    else:
        # Default to codepoints (regular Python len)
        return len(text)


def chunk_message(
    text: str,
    max_length: int = 4096,
    preserve_fences: bool = True,
    length_unit: str = "codepoints",
) -> List[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Splitting strategy (in priority order):
    1. **Paragraph boundaries** (blank lines ``\\n\\n``)
    2. **Sentence boundaries** (``. `` followed by uppercase or newline)
    3. **Hard split** at *max_length* (last resort)

    When *preserve_fences* is True, code fence blocks are never split
    even if they exceed *max_length*.

    Args:
        text: The message text to split.
        max_length: Maximum characters per chunk.
        preserve_fences: Keep code fences intact (default True).
        length_unit: Unit for length calculation ("codepoints" or "utf16").

    Returns:
        List of text chunks.
    """
    if not text:
        return [""]

    if _calculate_length(text, length_unit) <= max_length:
        return [text]

    # Split into paragraphs (double newline)
    paragraphs = re.split(r"\n\n", text)

    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para

        # Check if this paragraph is inside a fence span
        # If the candidate is small enough, accumulate
        if _calculate_length(candidate, length_unit) <= max_length:
            current = candidate
            continue

        # Candidate too long — flush current first
        if current:
            chunks.append(current.strip())
            current = ""

        # Now handle the paragraph itself
        if _calculate_length(para, length_unit) <= max_length:
            current = para
        elif preserve_fences and _is_fence_block(para):
            # Code fence block — keep intact even if over limit
            chunks.append(para.strip())
        else:
            # Paragraph too long — split at sentences or hard-split
            sub_chunks = _split_long_paragraph(para, max_length, length_unit)
            chunks.extend(sub_chunks[:-1])
            current = sub_chunks[-1] if sub_chunks else ""

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [""]


def enforce_hard_cap(
    chunks: List[str],
    max_length: int,
    length_unit: str = "codepoints",
) -> List[str]:
    """Guarantee every chunk fits within *max_length*.

    ``chunk_message`` intentionally emits an over-cap chunk when a single code
    fence exceeds *max_length* (``preserve_fences``). No platform client splits
    an oversized payload, so sending such a chunk raises "message too long" and
    the whole reply is lost. Callers apply this final pass so delivery always
    succeeds: any over-cap chunk is hard-split, and a split fence has its
    ``` markers re-balanced so each piece stays valid markdown (Issue #4319).

    Returns:
        A list of chunks each at most *max_length* long.
    """
    result: List[str] = []
    for chunk in chunks:
        if _calculate_length(chunk, length_unit) <= max_length:
            result.append(chunk)
            continue

        if _is_pure_fence_block(chunk):
            result.extend(_split_fence_block(chunk, max_length, length_unit))
        else:
            result.extend(_split_long_paragraph(chunk, max_length, length_unit))
    return result


def _split_fence_block(
    text: str, max_length: int, length_unit: str = "codepoints"
) -> List[str]:
    """Hard-split an over-cap code fence, re-balancing ``` on each piece.

    Only ever called on a *pure* fence block (see ``_is_pure_fence_block``):
    a single opening fence, an optional trailing close, and no interior fence
    markers. Wrapping the body in a fresh fence per piece is therefore safe and
    never turns prose into code (Issue #4319).
    """
    stripped = text.strip()
    lines = stripped.split("\n")
    # Opening fence line carries the optional language hint (e.g. ```python).
    fence_open = lines[0] if lines and lines[0].startswith("```") else "```"
    fence_lang = fence_open[3:].strip()
    reopen = "```" + fence_lang if fence_lang else "```"

    # Body excludes the opening fence and a trailing closing fence if present.
    body_lines = lines[1:]
    if body_lines and body_lines[-1].strip() == "```":
        body_lines = body_lines[:-1]
    body = "\n".join(body_lines)

    # Reserve room for the wrapping fences on each emitted piece.
    wrapper = _calculate_length(reopen + "\n" + "\n```", length_unit)
    inner_cap = max(1, max_length - wrapper)

    pieces = _split_long_paragraph(body, inner_cap, length_unit)
    return [f"{reopen}\n{piece}\n```" for piece in pieces if piece]


def _is_fence_block(text: str) -> bool:
    """Check if text starts with a code fence marker."""
    stripped = text.strip()
    return stripped.startswith("```")


def _is_pure_fence_block(text: str) -> bool:
    """True only for a single, self-contained code fence.

    A pure fence opens with ``` on its first line and contains no further fence
    markers except an optional closing ``` on the last line. Mixed content —
    a closed fence followed by prose, or multiple fences — is NOT pure: wrapping
    it in a fresh fence would render prose as code and corrupt the reply. Such
    chunks are hard-split as plain text instead (Issue #4319).
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return False

    lines = stripped.split("\n")
    # Count lines that are exactly a fence marker (``` optionally + language).
    fence_marker_lines = [
        i for i, line in enumerate(lines) if line.strip().startswith("```")
    ]

    # Opening fence must be the first line.
    if not fence_marker_lines or fence_marker_lines[0] != 0:
        return False

    # Allowed: just the opener (unterminated fence), or opener + a closing
    # marker on the final line. Anything else means interior/extra fences.
    if len(fence_marker_lines) == 1:
        return True
    if len(fence_marker_lines) == 2 and fence_marker_lines[1] == len(lines) - 1:
        return True
    return False


def _split_long_paragraph(text: str, max_length: int, length_unit: str = "codepoints") -> List[str]:
    """Split a long paragraph at sentence boundaries, then hard-split."""
    # Try sentence boundaries first
    sentences = re.split(r"(?<=[.!?])\s+", text)

    if len(sentences) > 1:
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            candidate = (current + " " + sentence) if current else sentence
            if _calculate_length(candidate, length_unit) <= max_length:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                if _calculate_length(sentence, length_unit) <= max_length:
                    current = sentence
                else:
                    # Sentence itself too long — hard split
                    chunks.extend(_hard_split(sentence, max_length, length_unit))
                    current = ""
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [""]

    # No sentence boundaries — hard split
    return _hard_split(text, max_length, length_unit)


def _hard_split(text: str, max_length: int, length_unit: str = "codepoints") -> List[str]:
    """Last-resort character-level split."""
    if length_unit == "utf16":
        # For UTF-16, we need to be more careful about splitting
        chunks = []
        start = 0
        while start < len(text):
            # Find the longest substring that fits
            end = start + max_length
            while end > start:
                chunk = text[start:end]
                if _calculate_length(chunk, length_unit) <= max_length:
                    chunks.append(chunk)
                    start = end
                    break
                end -= 1
            else:
                # Single character exceeds limit (shouldn't happen)
                chunks.append(text[start:start+1])
                start += 1
        return chunks
    else:
        # Simple codepoint split
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]
