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

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
