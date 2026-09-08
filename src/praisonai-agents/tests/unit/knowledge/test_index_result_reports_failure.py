"""``Knowledge.index()`` must not report success when nothing was indexed.

``IndexResult.success`` defaults to True and ``index()`` never assigned it. So a
run in which every file failed to embed still returned:

    IndexResult(success=True, files_indexed=0, chunks_created=0,
                errors=['/tmp/.../test.txt: Failed to generate embedding ...'])

Each failure was collected in ``errors`` and then contradicted by the flag a
caller actually branches on. ``if result.success:`` went on believing the corpus
was indexed.

Embedding is mocked here rather than marked ``live``, so the contract is
verified in CI instead of skipped with the tests that need a real provider.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from praisonaiagents.knowledge import Knowledge
from praisonaiagents.knowledge.models import AddResult


def _knowledge_with_add(add_impl):
    """A Knowledge whose store add() behaves as given, with no real backend."""
    knowledge = Knowledge.__new__(Knowledge)
    knowledge._corpus_stats = None
    knowledge._config = {}
    return knowledge, patch.object(Knowledge, "add", side_effect=add_impl)


def test_success_is_false_when_every_file_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "a.txt"), "w") as fh:
            fh.write("content")

        def boom(*args, **kwargs):
            raise RuntimeError("Failed to generate embedding (model=...)")

        with patch.object(Knowledge, "add", side_effect=boom):
            result = Knowledge().index(tmpdir)

        assert result.files_indexed == 0
        assert result.errors, "the failure was not recorded at all"
        assert result.success is False, (
            "reported success while indexing nothing and recording "
            f"{len(result.errors)} error(s)"
        )


def test_success_is_false_on_a_partial_failure():
    """Losing one file out of several must not be reported as success.

    A knowledge base quietly missing a document is the failure mode this whole
    result object exists to surface.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in ("good.txt", "bad.txt"):
            with open(os.path.join(tmpdir, name), "w") as fh:
                fh.write("content")

        def sometimes(*args, **kwargs):
            target = args[0] if args else kwargs.get("file_path", "")
            if "bad" in str(target):
                raise RuntimeError("Failed to generate embedding (model=...)")
            return AddResult(id="1", success=True)

        with patch.object(Knowledge, "add", side_effect=sometimes):
            result = Knowledge().index(tmpdir)

        assert len(result.errors) == 1
        assert result.success is False


def test_success_is_true_when_nothing_failed():
    """The guard must not become a blanket False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "a.txt"), "w") as fh:
            fh.write("content")

        with patch.object(Knowledge, "add",
                          return_value=AddResult(id="1", success=True)):
            result = Knowledge().index(tmpdir)

        assert result.errors == []
        assert result.success is True
