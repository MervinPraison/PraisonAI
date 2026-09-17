"""The chonkie embeddings import must fail with an actionable message.

Semantic / sdpm / late chunkers, and any string embedding_model, load
``chonkie.embeddings.AutoEmbeddings`` lazily via ``embedding_model``. When the
optional ``chonkie`` package is not installed, users should see the same
install hint the chunker import path already raises -- not a raw
``ModuleNotFoundError``.

A genuinely missing package is translated into the hint. But if ``chonkie``
is installed and its import fails for a different reason (e.g. a broken
transitive dependency), the original error must survive so the real cause is
not masked behind misleading install advice.
"""
import builtins
import re

import pytest

from praisonaiagents.knowledge.chunking import Chunking

HINT = "pip install 'praisonaiagents[knowledge]'"
HINT_RE = re.escape(HINT)


def _block_chonkie(monkeypatch, missing_top_level):
    """Simulate chonkie's embeddings import failing.

    ``missing_top_level`` decides whether the top-level ``chonkie`` package is
    considered installed, which is what the helper uses to choose between the
    actionable hint and re-raising the original error.
    """
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "chonkie.embeddings" or name.startswith("chonkie.embeddings."):
            raise ImportError("No module named 'chonkie.embeddings'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: None if (name == "chonkie" and missing_top_level) else object(),
    )


class TestAutoEmbeddingsImportGuard:

    @pytest.mark.parametrize("chunker_type", ["semantic", "sdpm", "late"])
    def test_default_semantic_path_raises_actionable_error(self, monkeypatch, chunker_type):
        _block_chonkie(monkeypatch, missing_top_level=True)
        chunking = Chunking(chunker_type=chunker_type)
        with pytest.raises(ImportError, match=HINT_RE):
            _ = chunking.embedding_model

    def test_string_model_path_raises_actionable_error(self, monkeypatch):
        _block_chonkie(monkeypatch, missing_top_level=True)
        chunking = Chunking(chunker_type="semantic", embedding_model="all-MiniLM-L6-v2")
        with pytest.raises(ImportError, match=HINT_RE):
            _ = chunking.embedding_model

    def test_installed_but_broken_import_is_not_masked(self, monkeypatch):
        """A transitive failure keeps its original message, no install hint."""
        _block_chonkie(monkeypatch, missing_top_level=False)
        chunking = Chunking(chunker_type="semantic")
        with pytest.raises(ImportError) as exc:
            _ = chunking.embedding_model
        assert HINT not in str(exc.value)

    def test_helper_returns_class_when_available(self):
        """When chonkie is installed the helper yields the real AutoEmbeddings."""
        chonkie_embeddings = pytest.importorskip("chonkie.embeddings")
        assert Chunking._import_auto_embeddings() is chonkie_embeddings.AutoEmbeddings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
