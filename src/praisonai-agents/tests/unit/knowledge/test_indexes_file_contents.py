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
    calls = []

    def build():
        k = Knowledge.__new__(Knowledge)
        k._verbose = 0

        def _store(content, **kw):
            calls.append((content, kw))
            stored.append(content)
            return {"ok": True}

        k.store = _store
        k.normalize_content = lambda c: c.strip().lower()
        k.__dict__["chunker"] = Chunking(
            chunker_type="recursive", chunk_size=200, chunk_overlap=20)
        return k

    return build, stored, calls


def _write(tmpdir, name, body):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


class TestUnlistedExtensionsAreRead:

    @pytest.mark.parametrize("name", ["auth.py", "app.ts", "main.go", "conf.yaml"])
    def test_source_files_store_their_contents(self, capture, name):
        build, stored, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, name, "def authenticate(user):\n    return bcrypt.check(user)\n")
            build()._process_single_input(path)
        assert stored, f"{name} indexed nothing"
        blob = "\n".join(stored)
        assert "bcrypt" in blob, f"{name} stored something other than its contents"
        assert path.lower() not in blob, f"{name} stored its own path as content"

    def test_the_path_is_never_the_content(self, capture):
        build, stored, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "notes.rst", "Release process\n===============\n")
            build()._process_single_input(path)
        assert stored[0].strip() != path.lower()

    def test_an_empty_file_is_refused_rather_than_stored(self, capture):
        build, _, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "empty.py", "   \n")
            with pytest.raises(ValueError):
                build()._process_single_input(path)

    def test_a_binary_file_is_refused_loudly(self, capture):
        """Better a clear error than a filename silently stored as knowledge."""
        build, _, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "blob.bin")
            with open(path, "wb") as fh:
                fh.write(b"\xff\xfe\x00\x01binary")
            with pytest.raises(ValueError):
                build()._process_single_input(path)

    def test_metadata_records_the_real_extension(self, capture):
        build, stored, calls = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "svc.py", "x = 1\n")
            build()._process_single_input(path, metadata={})
        assert stored
        assert calls[0][1]["metadata"]["file_type"] == "py"

    def test_suffixless_file_still_sets_file_type(self, capture):
        """A file such as `Dockerfile` or `.gitignore` has no suffix; the new
        metadata contract must still populate file_type (empty string) rather
        than omit it."""
        build, stored, calls = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "Dockerfile", "FROM python:3.12\nRUN pip install x\n")
            build()._process_single_input(path, metadata={})
        assert stored
        assert "file_type" in calls[0][1]["metadata"]
        assert calls[0][1]["metadata"]["file_type"] == ""

    def test_chunk_ending_in_txt_is_not_reopened_as_path(self, capture):
        """A source-file chunk that happens to end in `.txt`/`.pdf`/`.doc`/`.docx`
        must be stored verbatim, not re-dispatched through store()'s file-path
        heuristic where a non-existent path would be silently dropped."""
        build, stored, calls = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "loader.py", "open('missing_config.txt')")
            build()._process_single_input(path)
        assert stored, "chunk ending in .txt indexed nothing"
        assert any("missing_config.txt" in c for c in stored)
        assert all(kw.get("is_content") is True for _, kw in calls)


class TestExistingBehaviourIsPreserved:

    def test_raw_text_is_still_accepted(self, capture):
        """The branch was written for a caller passing prose, not a path."""
        build, stored, _ = capture
        build()._process_single_input("just some raw text, not a path")
        assert stored == ["just some raw text, not a path"]

    def test_a_listed_text_extension_still_works(self, capture):
        build, stored, _ = capture
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "notes.md", "# Design\nAuthentication uses bcrypt.\n")
            build()._process_single_input(path)
        assert "bcrypt" in "\n".join(stored)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
