"""Keep the knowledge unit tests off the network.

These are unit tests, but they drove the real embedding path: a socket recorder
showed `tests/unit/knowledge/test_indexing.py` alone reaching api.openai.com
(and raw.githubusercontent.com, litellm's price map). They failed with a 403
from whichever project the ambient key belonged to -- and on a machine with a
funded key they would have quietly spent money instead.

No workflow ran this directory, so neither the network access nor the failures
were visible.
"""

import hashlib

import pytest


def _hashing_vector(text: str, dims: int = 1536):
    """A bag-of-words hashing embedding: no network, but still meaningful.

    A constant-per-document stub is not enough here -- several suites store
    documents and assert that a query retrieves the right one, which needs an
    embedding where lexical overlap raises similarity. Hashing each token into
    a bucket and L2-normalising gives exactly that, deterministically.
    """
    import math
    import re

    vector = [0.0] * dims
    tokens = re.findall(r"[a-z0-9]+", str(text).lower())
    for token in tokens:
        bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % dims
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm:
        vector = [v / norm for v in vector]
    else:
        vector[0] = 1.0
    return vector


@pytest.fixture(autouse=True)
def _no_network_embeddings(monkeypatch, request):
    """Replace the embedding call for every test in this directory.

    Skipped for the suites that install their own embedding double -- those
    assert on failure handling, so a working stub would defeat them.
    """
    if request.node.fspath.basename in {"test_embedding_failure.py",
                                        "test_indexing_reports_failures.py",
                                        "test_provider_resolution.py"}:
        yield
        return
    class _Result:
        def __init__(self, texts, dims):
            self.embeddings = [_hashing_vector(t, dims) for t in texts]
            self.model = "stub-embedder"
            self.dimensions = dims

    def fake_embedding(input, model=None, dimensions=None, **kwargs):
        texts = [input] if isinstance(input, str) else list(input)
        return _Result(texts, dimensions or 1536)

    # The adapters do `from praisonaiagents.embedding import embedding`
    # inside the call, so patching the package attribute is enough and avoids
    # a name collision with a top-level `embedding` on sys.path.
    import importlib
    pkg = importlib.import_module("praisonaiagents.embedding")
    monkeypatch.setattr(pkg, "embedding", fake_embedding, raising=False)
    yield
