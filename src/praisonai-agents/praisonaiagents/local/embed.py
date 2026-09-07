"""Resolve a local embedding model, so a local agent stays local end to end.

The gap this closes: `Agent(llm="local", knowledge=[...])` routed chat to the
local server and embeddings to OpenAI, sending both the user's documents and
their queries off the machine with no warning. Ollama already serves
`nomic-embed-text` and friends; nothing asked it.

Data only, per the package contract: this returns a model name and an endpoint.
It never embeds anything.
"""

import os
from typing import Optional, Sequence, Tuple

from .capabilities import LocalEngine

__all__ = ["ENV_EMBED_MODEL", "PREFERRED_EMBED_MODELS",
           "select_embedding_model", "local_embedder_config",
           "remember_model_facts", "context_length_for", "embedding_dimension_for"]

# Facts the discovery probe already learned, kept so callers that cannot probe
# (a token budgeter on a hot path, an embedder factory) can still use them.
# Populated by resolve(); process-local; never triggers I/O of its own.
_MODEL_FACTS: dict = {}


def remember_model_facts(model_id, context_length=None, embedding_dimension=None) -> None:
    """Record what /api/show already told us about a model."""
    if not model_id:
        return
    facts = _MODEL_FACTS.setdefault(model_id, {})
    if context_length:
        facts["context_length"] = int(context_length)
    if embedding_dimension:
        facts["embedding_dimension"] = int(embedding_dimension)


def context_length_for(model_id):
    """The model's real context window, or None if we never probed it.

    Without this a local model inherits the generic 128000 default, so context
    compaction budgets a 40960-token model as if it had three times the room and
    the server truncates silently.
    """
    if not model_id:
        return None
    for key in (model_id, model_id.split("/", 1)[-1]):
        got = _MODEL_FACTS.get(key, {}).get("context_length")
        if got:
            return got
    return None


def embedding_dimension_for(model_id):
    """The embedder's real vector width, or None if unknown."""
    if not model_id:
        return None
    for key in (model_id, model_id.split("/", 1)[-1]):
        got = _MODEL_FACTS.get(key, {}).get("embedding_dimension")
        if got:
            return got
    return None

ENV_EMBED_MODEL = "PRAISONAI_LOCAL_EMBED_MODEL"

# Preference order when the caller names nothing. These are the embedders people
# actually pull for Ollama; the first one present wins. Order is quality-biased,
# not alphabetical: nomic-embed-text is the common default and outranks the
# smaller all-minilm.
PREFERRED_EMBED_MODELS = (
    "nomic-embed-text",
    "mxbai-embed-large",
    "bge-m3",
    "snowflake-arctic-embed",
    "all-minilm",
)


def _is_embedding_model(name: str, capabilities: Sequence[str]) -> bool:
    """True when a listed model can serve embeddings.

    Prefers the server's own capability list; falls back to the name for
    servers that report no capabilities at all.
    """
    if capabilities:
        return "embedding" in capabilities
    lowered = name.lower()
    return "embed" in lowered or lowered.startswith("bge-")


def select_embedding_model(
    models: Sequence[str],
    model_meta: Sequence[Tuple[str, Tuple[str, ...], Optional[str]]] = (),
) -> Optional[str]:
    """Pick an embedding model from what the server actually serves.

    Precedence: PRAISONAI_LOCAL_EMBED_MODEL (validated against the list) >
    PREFERRED_EMBED_MODELS order > any remaining embedding-capable model.
    Returns None when the server serves no embedding model -- callers must
    treat that as "cannot embed locally", never as "fall back to a cloud
    default".
    """
    caps_by_name = {name: caps for name, caps, _ in (model_meta or ())}
    embedders = [m for m in models
                 if _is_embedding_model(m, caps_by_name.get(m, ()))]
    if not embedders:
        return None

    named = (os.environ.get(ENV_EMBED_MODEL) or "").strip()
    if named:
        # Accept an exact id or a bare name the server tags (":latest").
        for candidate in embedders:
            if candidate == named or candidate.split(":", 1)[0] == named:
                return candidate
        return None

    for preferred in PREFERRED_EMBED_MODELS:
        for candidate in embedders:
            if candidate.split(":", 1)[0] == preferred:
                return candidate
    return embedders[0]


def local_embedder_config(engine: LocalEngine, base_url: str,
                          model: str) -> dict:
    """Build the embedder config block for a local engine.

    Shaped for the knowledge/memory layer (mem0-style provider + config).
    """
    dimension = embedding_dimension_for(model)
    if engine is LocalEngine.OLLAMA:
        config = {"model": model, "ollama_base_url": base_url}
        if dimension:
            # Without this the store is created at whatever the first vector
            # happens to be, or at a 1536 default that no local embedder emits.
            config["embedding_dims"] = dimension
        return {"provider": "ollama", "config": config}
    # Everything else speaks OpenAI over HTTP.
    trimmed = base_url.rstrip("/")
    config = {
        "model": model,
        "openai_base_url": trimmed if trimmed.endswith("/v1") else trimmed + "/v1",
    }
    if dimension:
        config["embedding_dims"] = dimension
    return {"provider": "openai", "config": config}
