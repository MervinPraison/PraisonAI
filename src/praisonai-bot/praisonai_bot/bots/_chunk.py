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


def _is_fence_block(text: str) -> bool:
    """Check if text is (or contains) a code fence block."""
    stripped = text.strip()
    return stripped.startswith("```")


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
