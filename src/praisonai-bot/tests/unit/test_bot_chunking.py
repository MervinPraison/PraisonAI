"""
TDD tests for bot markdown-aware message chunking.

Smart chunking splits long bot responses at paragraph boundaries
while preserving code fences and markdown structure.
"""

import pytest


class TestChunkMessage:
    """Tests for chunk_message function."""

    def _chunk(self, text, max_length=100, preserve_fences=True):
        from praisonai_bot.bots._chunk import chunk_message
        return chunk_message(text, max_length=max_length, preserve_fences=preserve_fences)

    def test_short_message_no_split(self):
        """Short messages are returned as single chunk."""
        chunks = self._chunk("Hello world!", max_length=100)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world!"

    def test_empty_message(self):
        """Empty message returns single empty chunk."""
        chunks = self._chunk("")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_split_at_paragraph_boundary(self):
        """Long text splits at paragraph boundaries (blank lines)."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = self._chunk(text, max_length=30)
        assert len(chunks) >= 2
        # Each chunk should contain complete paragraphs
        combined = "\n\n".join(chunks)
        assert "Paragraph one." in combined
        assert "Paragraph two." in combined
        assert "Paragraph three." in combined

    def test_never_split_inside_code_fence(self):
        """Code fences are kept intact even if they exceed max_length."""
        text = "Before\n\n```python\ndef hello():\n    print('Hello world!')\n    return True\n```\n\nAfter"
        chunks = self._chunk(text, max_length=50, preserve_fences=True)
        # The code fence should be in a single chunk
        fence_chunk = [c for c in chunks if "```python" in c]
        assert len(fence_chunk) == 1
        assert "```" in fence_chunk[0]
        # Fence must be properly closed
        assert fence_chunk[0].count("```") == 2

    def test_split_at_sentence_boundary_fallback(self):
        """If no paragraph breaks, split at sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        chunks = self._chunk(text, max_length=40)
        assert len(chunks) >= 2
        # No chunk should start mid-sentence (roughly)
        for chunk in chunks:
            assert len(chunk) <= 80  # Some tolerance

    def test_preserves_all_content(self):
        """All original content is preserved across chunks."""
        text = "A" * 50 + "\n\n" + "B" * 50 + "\n\n" + "C" * 50
        chunks = self._chunk(text, max_length=60)
        combined = "\n\n".join(chunks)
        assert "A" * 50 in combined
        assert "B" * 50 in combined
        assert "C" * 50 in combined

    def test_max_length_respected(self):
        """Chunks respect max_length (except for indivisible blocks)."""
        text = "Short.\n\n" + "Medium paragraph here.\n\n" + "Another one."
        chunks = self._chunk(text, max_length=30)
        for chunk in chunks:
            # Allow some tolerance for indivisible blocks
            assert len(chunk) <= 60 or "```" in chunk

    def test_multiple_code_fences(self):
        """Multiple code fences are each kept intact."""
        text = "Intro\n\n```js\nconsole.log('a');\n```\n\nMiddle\n\n```py\nprint('b')\n```\n\nEnd"
        chunks = self._chunk(text, max_length=40, preserve_fences=True)
        combined = "\n\n".join(chunks)
        assert combined.count("```js") == 1
        assert combined.count("```py") == 1

    def test_preserve_fences_false_allows_splitting(self):
        """With preserve_fences=False, code blocks can be split."""
        text = "```\n" + "x\n" * 100 + "```"
        chunks = self._chunk(text, max_length=50, preserve_fences=False)
        # Should be split since fences aren't preserved
        assert len(chunks) >= 2

    def test_single_long_line_gets_hard_split(self):
        """A single very long line with no breaks gets hard-split."""
        text = "A" * 500
        chunks = self._chunk(text, max_length=100)
        assert len(chunks) >= 5
        for chunk in chunks:
            assert len(chunk) <= 100


class TestEnforceHardCap:
    """Tests for enforce_hard_cap — the outbound over-cap guard (Issue #4319)."""

    def _cap(self, chunks, max_length):
        from praisonai_bot.bots._chunk import enforce_hard_cap
        return enforce_hard_cap(chunks, max_length)

    def test_under_cap_chunks_unchanged(self):
        """Chunks already within the cap pass through untouched."""
        chunks = ["short one", "short two"]
        assert self._cap(chunks, 100) == chunks

    def test_over_cap_prose_is_split(self):
        """An over-cap plain chunk is split so every piece fits."""
        big = "word " * 200  # ~1000 chars
        result = self._cap([big], 100)
        assert len(result) >= 2
        for piece in result:
            assert len(piece) <= 100

    def test_over_cap_fence_is_split_and_rebalanced(self):
        """An over-cap code fence is split with each piece a valid fence."""
        body = "\n".join(f"line {i}" for i in range(400))
        fence = "```python\n" + body + "\n```"
        assert len(fence) > 100
        result = self._cap([fence], 100)
        assert len(result) >= 2
        for piece in result:
            assert len(piece) <= 100
            # Each emitted piece is a balanced, valid fence.
            assert piece.count("```") == 2
            assert piece.startswith("```")
            assert piece.rstrip().endswith("```")

    def test_over_cap_fence_preserves_language_hint(self):
        """The language hint is carried onto every re-opened fence piece."""
        body = "\n".join(f"row{i}" for i in range(300))
        fence = "```json\n" + body + "\n```"
        result = self._cap([fence], 80)
        assert len(result) >= 2
        for piece in result:
            assert piece.startswith("```json")

    def test_no_content_lost_across_split_fence(self):
        """The source characters all survive the fence split (order preserved)."""
        body = "".join(f"payload-{i}\n" for i in range(50)).rstrip()
        fence = "```\n" + body + "\n```"
        result = self._cap([fence], 40)
        # Reassemble the inner bodies (strip the ``` wrappers each piece adds).
        inner = "".join(
            piece[3:].split("\n", 1)[1].rsplit("\n```", 1)[0]
            for piece in result
        )
        # Every non-whitespace character of the body is delivered, in order.
        assert inner.replace("\n", "") == body.replace("\n", "")

    def test_matches_the_reported_pure_fence_failure(self):
        """A ~9.8k pure fence is delivered as multiple capped chunks."""
        body = "\n".join("x" * 60 for _ in range(160))
        fence = "```\n" + body + "\n```"
        assert len(fence) > 4096
        result = self._cap([fence], 4096)
        assert len(result) >= 2
        for piece in result:
            assert len(piece) <= 4096

    def test_mixed_fence_and_prose_not_corrupted(self):
        """A closed fence followed by prose must NOT be re-wrapped as code.

        Greptile P1: ``_is_fence_block`` matched anything starting with ``` so a
        chunk of "closed fence + trailing prose" was wrapped in a fresh fence,
        rendering the prose as code. The chunk must instead be hard-split as
        plain text (Issue #4319).
        """
        prose = "This is prose that must stay prose. " * 10
        chunk = "```python\nprint('hi')\n```\n\n" + prose
        assert len(chunk) > 100
        result = self._cap([chunk], 100)
        combined = "\n".join(result)
        # The original prose survives verbatim somewhere in the output.
        assert "This is prose that must stay prose." in combined
        # No fabricated language-tagged fence wraps the prose.
        assert combined.count("```python") <= 1
        for piece in result:
            assert len(piece) <= 100

    def test_multiple_fences_in_one_chunk_not_rewrapped(self):
        """Two fences in one over-cap chunk are hard-split, not merged as code."""
        chunk = (
            "```\n" + ("a" * 60) + "\n```\n\n"
            "prose between fences\n\n"
            "```\n" + ("b" * 60) + "\n```"
        )
        result = self._cap([chunk], 50)
        combined = "\n".join(result)
        assert "prose between fences" in combined
        for piece in result:
            assert len(piece) <= 50


class TestUtf16LengthUnit:
    """Telegram measures length in UTF-16 units, not codepoints (Issue #4319)."""

    def test_emoji_chunks_respect_utf16_cap(self):
        """Emoji-heavy text is capped by UTF-16 units so Telegram won't reject it."""
        from praisonai_bot.bots._chunk import (
            chunk_message,
            enforce_hard_cap,
            _calculate_length,
        )

        # Each 😀 is 1 codepoint but 2 UTF-16 units. 200 emoji = 400 UTF-16.
        text = "😀" * 200
        max_len = 100
        chunks = chunk_message(text, max_length=max_len, length_unit="utf16")
        chunks = enforce_hard_cap(chunks, max_len, length_unit="utf16")
        for chunk in chunks:
            assert _calculate_length(chunk, "utf16") <= max_len

    def test_calculate_length_utf16_counts_surrogate_pairs(self):
        """A supplementary-plane char counts as 2 UTF-16 units, 1 codepoint."""
        from praisonai_bot.bots._chunk import _calculate_length

        assert _calculate_length("😀", "codepoints") == 1
        assert _calculate_length("😀", "utf16") == 2
