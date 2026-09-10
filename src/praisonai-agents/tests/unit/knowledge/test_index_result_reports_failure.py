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


def test_success_is_false_on_partial_chunk_loss_within_a_file():
    """Some chunks of a file storing and some being swallowed is a partial loss.

    ``_process_single_input`` only raises when *every* chunk fails, so a file
    where a subset of chunks fell into ``store()``'s falsy-return path returned
    normally with a shorter ``results`` list and no error -- leaving
    ``result.success`` True while part of the document was silently dropped.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "doc.txt"), "w") as fh:
            fh.write("content")

        knowledge = Knowledge()

        call_count = {"n": 0}

        def flaky_store(memory, *args, **kwargs):
            # First chunk lands, second is swallowed (store() returns falsy).
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"results": [{"id": "1"}]}
            return []

        # Two chunks so one can succeed and one fail.
        with patch.object(knowledge.chunker, "chunk",
                          return_value=["chunk one", "chunk two"]), \
             patch.object(knowledge, "store", side_effect=flaky_store):
            result = knowledge.index(tmpdir)

        assert result.errors, "partial chunk loss was not recorded"
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
