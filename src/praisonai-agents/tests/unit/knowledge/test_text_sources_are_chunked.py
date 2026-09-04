"""Text sources must be chunked, like every other source.

`_process_single_input` has three branches. The document/media branch chunks.
The unlisted-extension branch chunks. The `text` branch -- .txt .csv .json
.xml .md .html .htm, which is what most people actually index -- stored the
whole file as ONE memory and lowercased it:

    memories = [self.normalize_content(content)]

So `chunk_size` and `chunk_overlap` were inert on the commonest path. A 20 KB
guide became a single 20 KB memory that no retrieval could rank usefully, and
the case of every identifier and proper noun was destroyed on the way to the
model. Measured before the fix, with chunk_size=200:

    guide.md    memories=  1  largest=20817  lowercased=True
    notes.rst   memories= 30  largest=  695  lowercased=False   <- other branch

The asymmetry is the tell: the same content, indexed two ways, depending only
on the file extension.
"""
import os
import tempfile

import pytest

from praisonaiagents.knowledge.chunking import Chunking
from praisonaiagents.knowledge.knowledge import Knowledge

BODY = "\n\n".join(
    f"Section {i}: The Quick Brown Fox jumped over the LAZY dog. " * 12
    for i in range(30)
)


def _index(name, body=BODY, chunk_size=200):
    stored = []
    k = Knowledge.__new__(Knowledge)
    k._verbose = 0
    k.store = lambda content, **kw: stored.append(content) or {"ok": True}
    k.normalize_content = lambda c: c.strip().lower()
    k.__dict__["chunker"] = Chunking(
        chunker_type="recursive", chunk_size=chunk_size, chunk_overlap=20)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        k._process_single_input(path)
    return stored


class TestTextSourcesAreChunked:

    @pytest.mark.parametrize("name", ["guide.md", "data.txt", "notes.html"])
    def test_a_large_file_becomes_many_memories(self, name):
        stored = _index(name)
        assert len(stored) > 1, (
            f"{name} was stored as a single memory; chunk_size was ignored"
        )

    @pytest.mark.parametrize("name", ["guide.md", "data.txt"])
    def test_no_memory_is_the_whole_file(self, name):
        stored = _index(name)
        assert max(len(s) for s in stored) < len(BODY), (
            f"{name} produced a memory as large as the source file"
        )

    def test_chunk_size_actually_changes_the_result(self):
        """The setting must do something, not merely be accepted."""
        small = _index("guide.md", chunk_size=200)
        large = _index("guide.md", chunk_size=4000)
        assert len(small) > len(large), (
            "chunk_size had no effect on the number of chunks"
        )

    @pytest.mark.parametrize("name", ["guide.md", "data.txt"])
    def test_case_is_preserved(self, name):
        """Lowercasing destroys identifiers and proper nouns in the answer."""
        assert "LAZY" in " ".join(_index(name)), f"{name} was lowercased"

    def test_all_three_branches_agree(self):
        """Same content, three extensions, one behaviour.

        .md goes through the text branch and .rst through the unlisted-extension
        branch. They disagreed completely before this fix.
        """
        counts = {n: len(_index(n)) for n in ("guide.md", "data.txt", "notes.rst")}
        assert len(set(counts.values())) == 1, (
            f"the same content indexed differently by extension: {counts}"
        )

    def test_a_short_file_still_produces_content(self):
        """Chunking must not lose a file smaller than one chunk."""
        stored = _index("tiny.md", body="Authentication uses bcrypt.")
        assert stored and "bcrypt" in " ".join(stored)

    def test_an_empty_file_is_still_refused(self):
        with pytest.raises(ValueError):
            _index("empty.md", body="   \n")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
