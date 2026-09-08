"""Indexing a directory must tell the caller which files failed.

The directory walk caught per-file exceptions, logged them at WARNING, and
dropped them:

    except Exception as e:
        logger.warning(f"Failed to process file {file_path}: {e}")

then returned `{'results': [...], 'relations': []}`. So a directory whose
every file failed to embed -- a wrong model, a revoked key, an exhausted
quota -- returned a success-shaped result with an empty list, and the caller
believed the knowledge base was populated. The only trace was a warning in a
log nobody reads during a bulk import.

This is how the repo's own knowledge tests came to fail confusingly: their
skip-guard never fired, because no exception ever escaped for it to catch.
"""
import os
import tempfile

import pytest

# These tests build a bare Knowledge instance via __new__ and mock store(), so
# no embedding backend is ever reached. Do NOT install a fake OPENAI_API_KEY at
# import time -- a module-level env mutation persists for the whole test process
# and can make later provider-backed tests mistake it for a real credential.
from praisonaiagents.knowledge.chunking import Chunking
from praisonaiagents.knowledge.knowledge import Knowledge


@pytest.fixture
def docs_dir():
    with tempfile.TemporaryDirectory() as d:
        for name in ("a.md", "b.md", "c.md"):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write("Authentication uses bcrypt.\n")
        yield d


def _index(docs_dir, store_fn):
    k = Knowledge.__new__(Knowledge)
    k._verbose = 0
    k.store = store_fn
    k.normalize_content = lambda c: c.strip().lower()
    k.__dict__["chunker"] = Chunking(
        chunker_type="recursive", chunk_size=200, chunk_overlap=20)
    k._emit_knowledge_event = lambda *a, **kw: None
    return k._process_single_input(docs_dir)


def _boom(content, **kw):
    raise RuntimeError("Failed to generate embedding (model=text-embedding-3-small)")


def _ok(content, **kw):
    return {"results": ["id"]}


def _swallowed(content, **kw):
    # Mirrors the real store(): it catches the embedding exception and returns an
    # empty list instead of raising. Without surfacing, this reads as success.
    return []


class TestFailuresReachTheCaller:

    def test_a_wholly_failed_import_is_not_silent(self, docs_dir):
        result = _index(docs_dir, _boom)
        assert result.get("errors"), (
            "every file failed and the caller was told nothing"
        )

    def test_every_failure_is_listed(self, docs_dir):
        result = _index(docs_dir, _boom)
        assert len(result["errors"]) == 3

    def test_the_error_names_the_file_and_the_reason(self, docs_dir):
        entry = _index(docs_dir, _boom)["errors"][0]
        assert entry["file"].endswith(".md")
        assert "embedding" in entry["error"].lower()

    def test_a_clean_import_reports_no_errors(self, docs_dir):
        result = _index(docs_dir, _ok)
        assert result["errors"] == []
        assert len(result["results"]) == 3

    def test_partial_failure_reports_both_sides(self, docs_dir):
        seen = {"n": 0}

        def flaky(content, **kw):
            seen["n"] += 1
            if seen["n"] == 1:
                raise RuntimeError("Failed to generate embedding")
            return {"results": ["id"]}

        result = _index(docs_dir, flaky)
        assert len(result["errors"]) == 1
        assert len(result["results"]) == 2, "the surviving files were lost too"

    def test_the_existing_result_shape_is_preserved(self, docs_dir):
        """Callers already read 'results' and 'relations'."""
        result = _index(docs_dir, _ok)
        assert "results" in result and "relations" in result

    def test_store_that_swallows_the_error_is_still_reported(self, docs_dir):
        """The production store() returns [] on embedding failure rather than
        raising. That must still surface as an error, not a false success."""
        result = _index(docs_dir, _swallowed)
        assert result["results"] == []
        assert len(result["errors"]) == 3, (
            "store() swallowed the failure and the caller was told nothing"
        )

    def test_list_input_propagates_directory_errors(self, docs_dir):
        """add([dir]) must not drop the per-file errors the directory collected."""
        k = Knowledge.__new__(Knowledge)
        k._verbose = 0
        k.store = _boom
        k.normalize_content = lambda c: c.strip().lower()
        k.__dict__["chunker"] = Chunking(
            chunker_type="recursive", chunk_size=200, chunk_overlap=20)
        k._emit_knowledge_event = lambda *a, **kw: None
        result = k.add([docs_dir])
        assert len(result["errors"]) == 3
        assert result["results"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestIndexResultSuccessReflectsErrors:
    """IndexResult.success must not be True when every file failed.

    `success: bool = True` was a dataclass default that NOTHING ever assigned --
    no `result.success = ...` existed anywhere in the package. So index()
    returned success=True unconditionally: a directory whose every file failed
    to embed (revoked key, wrong model, exhausted quota) came back as
    IndexResult(success=True, files_indexed=0, errors=[...3 entries...]).

    Nothing read the field either, which is why no test caught it -- the bug was
    invisible until you believed the flag instead of the counts.
    """

    def _knowledge(self, add_fn):
        k = Knowledge.__new__(Knowledge)
        k._verbose = 0
        k.add = add_fn
        k._emit_knowledge_event = lambda *a, **kw: None
        return k

    def test_success_is_false_when_every_file_fails(self, docs_dir):
        def _fail(filepath, **kw):
            raise RuntimeError("embedding backend unreachable")

        result = self._knowledge(_fail).index(docs_dir, incremental=False)

        assert result.files_indexed == 0
        assert len(result.errors) == 3
        assert result.success is False, (
            "index() reported success while every file failed to embed"
        )

    def test_success_is_false_on_partial_failure(self, docs_dir):
        seen = []

        def _flaky(filepath, **kw):
            seen.append(filepath)
            if len(seen) == 1:
                raise RuntimeError("embedding backend unreachable")
            return {"results": [{"id": "x"}]}

        result = self._knowledge(_flaky).index(docs_dir, incremental=False)

        assert result.files_indexed == 2
        assert len(result.errors) == 1
        assert result.success is False

    def test_success_is_true_when_nothing_failed(self, docs_dir):
        """The control: without this, `success = not errors` could just be False."""
        def _ok_add(filepath, **kw):
            return {"results": [{"id": "x"}]}

        result = self._knowledge(_ok_add).index(docs_dir, incremental=False)

        assert result.files_indexed == 3
        assert result.errors == []
        assert result.success is True
