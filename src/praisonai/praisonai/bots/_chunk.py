"""
Markdown-aware message chunking for PraisonAI bots.

Splits long bot responses at paragraph boundaries while preserving
code fences and markdown structure.  Inspired by OpenClaw's chunk.ts
but kept minimal (~120 lines).

Usage::

    from praisonai.bots._chunk import chunk_message

    chunks = chunk_message(text, max_length=4096, preserve_fences=True)
    for chunk in chunks:
        await bot.send_message(channel_id, chunk)
"""

from __future__ import annotations

import re
from typing import List


def chunk_message(
    text: str,
    max_length: int = 4096,
    preserve_fences: bool = True,
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

    Returns:
        List of text chunks.
    """
    if not text:
        return [""]

    if len(text) <= max_length:
        return [text]

    # Split into paragraphs (double newline)
    paragraphs = re.split(r"\n\n", text)

    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        candidate = (current + "\n\n" + para) if current else para

        # Check if this paragraph is inside a fence span
        # If the candidate is small enough, accumulate
        if len(candidate) <= max_length:
            current = candidate
            continue

        # Candidate too long — flush current first
        if current:
            chunks.append(current.strip())
            current = ""

        # Now handle the paragraph itself
        if len(para) <= max_length:
            current = para
        elif preserve_fences and _is_fence_block(para):
            # Code fence block — keep intact even if over limit
            chunks.append(para.strip())
        else:
            # Paragraph too long — split at sentences or hard-split
            sub_chunks = _split_long_paragraph(para, max_length)
            chunks.extend(sub_chunks[:-1])
            current = sub_chunks[-1] if sub_chunks else ""

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [""]


def _is_fence_block(text: str) -> bool:
    """Check if text is (or contains) a code fence block."""
    stripped = text.strip()
    return stripped.startswith("```")


def _split_long_paragraph(text: str, max_length: int) -> List[str]:
    """Split a long paragraph at sentence boundaries, then hard-split."""
    # Try sentence boundaries first
    sentences = re.split(r"(?<=[.!?])\s+", text)

    if len(sentences) > 1:
        chunks: List[str] = []
        current = ""
        for sentence in sentences:
            candidate = (current + " " + sentence) if current else sentence
            if len(candidate) <= max_length:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                if len(sentence) <= max_length:
                    current = sentence
                else:
                    # Sentence itself too long — hard split
                    chunks.extend(_hard_split(sentence, max_length))
                    current = ""
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [""]

    # No sentence boundaries — hard split
    return _hard_split(text, max_length)


def _hard_split(text: str, max_length: int) -> List[str]:
    """Last-resort character-level split."""
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]
