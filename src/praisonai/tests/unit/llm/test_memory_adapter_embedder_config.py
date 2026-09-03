"""A configured embedding model must reach the adapter that embeds.

`MongoDBMemoryAdapter._get_embedding` hardcoded "text-embedding-3-small" and its
`__init__` stored nothing about embeddings, so there was no configuration path
at all: an agent configured entirely against a local runtime still embedded
against OpenAI, silently.

These tests exercise the config plumbing with the embedding call itself patched.
No network, no MongoDB.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_adapter(**kwargs):
    """Build a MongoDBMemoryAdapter with pymongo and the client fully faked."""
    from praisonaiagents.memory.adapters.factories import MongoDBMemoryAdapter

    fake_pymongo = MagicMock()
    fake_client_factory = MagicMock()
    client = fake_client_factory.return_value
    client.admin.command.return_value = {"ok": 1}
    return MongoDBMemoryAdapter(fake_pymongo, fake_client_factory, **kwargs)


def _captured_model(adapter):
    """Call _get_embedding with the embedding function patched; return the model."""
    seen = {}

    def fake_embedding(text, model=None, **kw):
        seen["model"] = model
        result = MagicMock()
        result.embeddings = [[0.0, 0.1]]
        return result

    mod = types.ModuleType("praisonaiagents.embedding")
    mod.embedding = fake_embedding
    with patch.dict(sys.modules, {"praisonaiagents.embedding": mod}):
        adapter._get_embedding("some text")
    return seen.get("model")


def test_configured_embedding_model_is_used():
    """The whole defect: a configured local embedder must actually be used."""
    adapter = _make_adapter(config={"embedding_model": "nomic-embed-text"})
    assert _captured_model(adapter) == "nomic-embed-text"


def test_embedder_block_form_is_honoured():
    """The `embedder` config shape used elsewhere in the memory layer.

    The provider must be recombined with the model into litellm's
    "<provider>/<model>" form, otherwise a bare local model name is sent to
    the OpenAI default endpoint and never reaches the local runtime.
    Mirrors knowledge/adapters/mongodb_adapter._init_embedding_model.
    """
    adapter = _make_adapter(
        config={"embedder": {"provider": "ollama", "config": {"model": "mxbai-embed-large"}}}
    )
    assert _captured_model(adapter) == "ollama/mxbai-embed-large"


def test_embedder_block_openai_provider_stays_bare():
    """OpenAI is the litellm default, so its models keep their bare name."""
    adapter = _make_adapter(
        config={"embedder": {"provider": "openai", "config": {"model": "text-embedding-3-large"}}}
    )
    assert _captured_model(adapter) == "text-embedding-3-large"


def test_embedder_block_without_provider_stays_bare():
    """A model with no provider is left untouched (backward compatible)."""
    adapter = _make_adapter(
        config={"embedder": {"config": {"model": "nomic-embed-text"}}}
    )
    assert _captured_model(adapter) == "nomic-embed-text"


def test_top_level_embedding_model_kwarg_is_honoured():
    adapter = _make_adapter(embedding_model="all-minilm")
    assert _captured_model(adapter) == "all-minilm"


def test_config_wins_over_the_hardcoded_default():
    adapter = _make_adapter(config={"embedding_model": "nomic-embed-text"})
    assert _captured_model(adapter) != "text-embedding-3-small"


def test_default_is_unchanged_when_nothing_is_configured():
    """Backward compatibility: no config still means the OpenAI default."""
    adapter = _make_adapter()
    assert _captured_model(adapter) == "text-embedding-3-small"
