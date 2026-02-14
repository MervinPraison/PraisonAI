"""
TDD tests for bot markdown-aware message chunking.

Smart chunking splits long bot responses at paragraph boundaries
while preserving code fences and markdown structure.
"""

import pytest


class TestChunkMessage:
    """Tests for chunk_message function."""

    def _chunk(self, text, max_length=100, preserve_fences=True):
        from praisonai.bots._chunk import chunk_message
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
