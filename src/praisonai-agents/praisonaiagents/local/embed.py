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
           "select_embedding_model", "local_embedder_config"]

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
    if engine is LocalEngine.OLLAMA:
        return {
            "provider": "ollama",
            "config": {"model": model, "ollama_base_url": base_url},
        }
    # Everything else speaks OpenAI over HTTP.
    trimmed = base_url.rstrip("/")
    return {
        "provider": "openai",
        "config": {
            "model": model,
            "openai_base_url": trimmed if trimmed.endswith("/v1") else trimmed + "/v1",
        },
    }
