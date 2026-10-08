"""
Embeddings Capabilities Module

Re-exports the single canonical embedding surface from the Core SDK
(``praisonaiagents.embedding``) so that there is exactly one
``EmbeddingResult`` type across the public API.

Previously this module redefined its own ``EmbeddingResult`` dataclass and
``embed``/``aembed`` implementations, which meant
``praisonai.EmbeddingResult`` (Core SDK) and
``praisonai.capabilities.EmbeddingResult`` (this module) were two different
classes — so ``isinstance(result, EmbeddingResult)`` depended on which import
a caller happened to pick. They now point at the same implementation.
"""

from praisonaiagents.embedding import EmbeddingResult
from praisonaiagents.embedding.embed import (
    embed,
    aembed,
    embedding,
    aembedding,
)

__all__ = [
    "EmbeddingResult",
    "embed",
    "aembed",
    "embedding",
    "aembedding",
]
