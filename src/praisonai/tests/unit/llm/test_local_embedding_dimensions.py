"""Local embedding models must not be silently sized as OpenAI models.

`get_dimensions` fell back to DEFAULT_DIMENSION (1536, OpenAI's) for every model
it did not recognise, and it recognised no locally-served embedder. A vector
index built for a local embedder was therefore created at 1536 dimensions while
the model produced 768 or 384 -- a 2x or 4x mismatch, with no warning.

Dimensions marked "measured" below were obtained by embedding a probe string
through a live Ollama 0.33.2 and counting the returned vector, and cross-checked
against the `<family>.embedding_length` field of /api/show.
"""

import pytest

from praisonaiagents.embedding.dimensions import DEFAULT_DIMENSION, get_dimensions


# (model tag, dimension, how it was established)
LOCAL_EMBEDDERS = [
    ("nomic-embed-text", 768, "measured"),
    ("all-minilm", 384, "measured"),
    ("mxbai-embed-large", 1024, "measured"),
]


@pytest.mark.parametrize("model, expected, _how", LOCAL_EMBEDDERS)
def test_local_embedder_dimensions(model, expected, _how):
    assert get_dimensions(model) == expected, (
        f"{model} sized as {get_dimensions(model)}; a vector index built at that "
        f"size cannot hold its {expected}-dimension vectors"
    )


@pytest.mark.parametrize("model, expected, _how", LOCAL_EMBEDDERS)
def test_local_embedder_is_not_the_openai_default(model, expected, _how):
    """The specific failure: silently inheriting OpenAI's 1536."""
    if expected != DEFAULT_DIMENSION:
        assert get_dimensions(model) != DEFAULT_DIMENSION


def test_ollama_prefixed_tag_resolves():
    """Users write the litellm form; it must resolve the same."""
    assert get_dimensions("ollama/nomic-embed-text") == 768


def test_versioned_tag_resolves():
    """Ollama tags carry a :tag suffix."""
    assert get_dimensions("nomic-embed-text:latest") == 768
    assert get_dimensions("nomic-embed-text:v1.5") == 768


def test_all_minilm_short_tag_matches_the_long_name():
    """Ollama's tag is `all-minilm`; the table's key was `all-MiniLM-L6-v2`.

    The substring lookup went the wrong way -- the long key is not contained in
    the short tag -- so Ollama's own naming missed a model the table already knew.
    """
    assert get_dimensions("all-minilm") == get_dimensions("all-MiniLM-L6-v2") == 384


# --- unchanged behaviour ------------------------------------------------------

@pytest.mark.parametrize(
    "model, expected",
    [
        ("text-embedding-3-small", 1536),
        ("text-embedding-3-large", 3072),
        ("text-embedding-ada-002", 1536),
        ("embed-english-v3.0", 1024),
        ("voyage-3-lite", 512),
        ("bge-base-en-v1.5", 768),
    ],
)
def test_existing_models_unchanged(model, expected):
    assert get_dimensions(model) == expected


def test_unknown_model_still_falls_back():
    assert get_dimensions("some-model-nobody-has-heard-of") == DEFAULT_DIMENSION
