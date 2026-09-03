"""Indexing a file must store its contents, not its path.

`_process_single_input` decided what to do from a hard-coded extension table
(.pdf .doc .txt .md .csv .json .xml .html, media, .zip). Anything else fell to
a branch commented "Treat as raw text content only if no file extension" —

    memories = [self.normalize_content(input_path)]

— which stored the PATH, lowercased. Every source file lands there: .py .js
.ts .go .rs .java .yaml .toml .sh .ipynb .rst. So indexing a repository built
a knowledge base of lowercased filenames and reported success, and retrieval
found nothing, with no error at any point.

The raw-text case the branch was written for still has to work: a caller may
pass a string of prose rather than a path.
"""
import os
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.knowledge.chunking import Chunking
from praisonaiagents.knowledge.knowledge import Knowledge


@pytest.fixture
def capture():
    """A Knowledge with the vector store replaced by a list."""
    stored = []

    def build():
        k = Knowledge.__new__(Knowledge)
        k._verbose = 0
        k.store = lambda content, **kw: stored.append(content) or {"ok": True}
        k.normalize_content = lambda c: c.strip().lower()
        k.__dict__["chunker"] = Chunking(
            chunker_type="recursive", chunk_size=200, chunk_overlap=20)
        return k

    return build, stored


def _write(tmpdir, name, body):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


class TestUnlistedExtensionsAreRead:

    @pytest.mark.parametrize("name", ["auth.py", "app.ts", "main.go", "conf.yaml"])
    def test_source_files_store_their_contents(self, capture, name):
        build, stored = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, name, "def authenticate(user):\n    return bcrypt.check(user)\n")
            build()._process_single_input(path)
        assert stored, f"{name} indexed nothing"
        blob = "\n".join(stored)
        assert "bcrypt" in blob, f"{name} stored something other than its contents"
        assert path.lower() not in blob, f"{name} stored its own path as content"

    def test_the_path_is_never_the_content(self, capture):
        build, stored = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "notes.rst", "Release process\n===============\n")
            build()._process_single_input(path)
        assert stored[0].strip() != path.lower()

    def test_an_empty_file_is_refused_rather_than_stored(self, capture):
        build, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "empty.py", "   \n")
            with pytest.raises(ValueError):
                build()._process_single_input(path)

    def test_a_binary_file_is_refused_loudly(self, capture):
        """Better a clear error than a filename silently stored as knowledge."""
        build, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "blob.bin")
            with open(path, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x01binary")
            with pytest.raises(ValueError):
                build()._process_single_input(path)

    def test_metadata_records_the_real_extension(self, capture):
        build, stored = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "svc.py", "x = 1\n")
            build()._process_single_input(path, metadata={})
        assert stored


class TestExistingBehaviourIsPreserved:

    def test_raw_text_is_still_accepted(self, capture):
        """The branch was written for a caller passing prose, not a path."""
        build, stored = capture
        build()._process_single_input("just some raw text, not a path")
        assert stored == ["just some raw text, not a path"]

    def test_a_listed_text_extension_still_works(self, capture):
        build, stored = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "notes.md", "# Design\nAuthentication uses bcrypt.\n")
            build()._process_single_input(path)
        assert "bcrypt" in "\n".join(stored)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
