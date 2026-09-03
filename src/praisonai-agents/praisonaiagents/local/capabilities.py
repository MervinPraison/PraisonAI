"""Local-engine vocabulary and capability resolution.

Layer 0 of ``praisonaiagents.local``: standard library only, no sibling imports
beyond none at all. This module owns the shared vocabulary (``LocalEngine``,
``ApiStyle``, ``Cap``, ``Evidence``) as well as the capability parsers, because
that is the only placement that keeps the package's import graph acyclic.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

__all__ = [
    "LocalEngine", "ApiStyle", "Cap", "Evidence",
    "DEFAULT_CAPS", "default_caps",
    "parse_ollama_capabilities", "parse_llama_cpp_props",
    "parse_lm_studio_models", "parse_openai_models",
]


class LocalEngine(str, Enum):
    """A local model server. Never called "runtime": that name is taken."""

    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    MLX_LM = "mlx_lm"
    LM_STUDIO = "lm_studio"
    VLLM = "vllm"
    TRANSFORMERS_SERVE = "transformers_serve"
    LLAMAFILE = "llamafile"
    LOCALAI = "localai"
    RAMALAMA = "ramalama"
    UNKNOWN = "unknown"


class ApiStyle(str, Enum):
    OPENAI_CHAT = "openai_chat"
    OPENAI_COMPLETIONS = "openai_completions"
    OLLAMA_NATIVE = "ollama_native"


class Cap(str, Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    TOOLS = "tools"
    VISION = "vision"
    AUDIO_IN = "audio_in"
    THINKING = "thinking"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"
    STREAMING = "streaming"
    STREAMING_WITH_TOOLS = "streaming_with_tools"
    PARALLEL_TOOL_CALLS = "parallel_tool_calls"
    EMBEDDINGS_ENDPOINT = "embeddings_endpoint"


class Evidence(str, Enum):
    """Where a field's value came from. Keeps guesses distinguishable from facts."""

    SERVER = "server"
    TABLE = "table"
    ENV = "env"
    SPEC = "spec"
    UNKNOWN = "unknown"


# Static per-engine floor. Cap.TOOLS and Cap.VISION are deliberately absent from
# every row: claiming them without server evidence is exactly the silent failure
# this package exists to prevent.
DEFAULT_CAPS: Mapping[LocalEngine, frozenset] = {
    LocalEngine.OLLAMA: frozenset({
        Cap.CHAT, Cap.COMPLETION, Cap.STREAMING, Cap.JSON_OBJECT,
        Cap.JSON_SCHEMA, Cap.EMBEDDINGS_ENDPOINT}),
    LocalEngine.LLAMA_CPP: frozenset({
        Cap.CHAT, Cap.COMPLETION, Cap.STREAMING, Cap.JSON_SCHEMA,
        Cap.JSON_OBJECT, Cap.EMBEDDINGS_ENDPOINT}),
    LocalEngine.MLX_LM: frozenset({Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}),
    LocalEngine.LM_STUDIO: frozenset({
        Cap.CHAT, Cap.COMPLETION, Cap.STREAMING, Cap.JSON_SCHEMA,
        Cap.JSON_OBJECT, Cap.EMBEDDINGS_ENDPOINT}),
    LocalEngine.VLLM: frozenset({
        Cap.CHAT, Cap.COMPLETION, Cap.STREAMING, Cap.JSON_SCHEMA, Cap.JSON_OBJECT,
        Cap.EMBEDDINGS_ENDPOINT, Cap.PARALLEL_TOOL_CALLS}),
    LocalEngine.TRANSFORMERS_SERVE: frozenset({Cap.CHAT, Cap.STREAMING}),
    LocalEngine.LLAMAFILE: frozenset({Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}),
    LocalEngine.LOCALAI: frozenset({Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}),
    LocalEngine.RAMALAMA: frozenset({Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}),
    LocalEngine.UNKNOWN: frozenset({Cap.CHAT, Cap.STREAMING}),
}


def default_caps(engine) -> frozenset:
    """Return the static per-engine capability floor (no network, Evidence.TABLE)."""
    try:
        return DEFAULT_CAPS[LocalEngine(engine)]
    except (KeyError, ValueError):
        return DEFAULT_CAPS[LocalEngine.UNKNOWN]


_OLLAMA_CAP_MAP = {
    "completion": (Cap.COMPLETION, Cap.CHAT),
    "tools": (Cap.TOOLS,),
    "vision": (Cap.VISION,),
    "thinking": (Cap.THINKING,),
    "embedding": (Cap.EMBEDDINGS_ENDPOINT,),
    "audio": (Cap.AUDIO_IN,),
}


def parse_ollama_capabilities(payload: Mapping[str, Any]) -> frozenset:
    """Map an Ollama /api/show or /api/tags entry's ``capabilities`` list onto Cap.

    Unknown strings ("insert", anything new) are ignored rather than raised on,
    so a newer Ollama cannot break resolution.
    """
    out = set()
    try:
        for name in payload.get("capabilities") or ():
            out.update(_OLLAMA_CAP_MAP.get(str(name).lower(), ()))
    except AttributeError:
        return frozenset()
    return frozenset(out)


def parse_llama_cpp_props(payload: Mapping[str, Any]) -> frozenset:
    """Map a llama.cpp GET /props reply onto Cap."""
    out = {Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}
    try:
        modalities = payload.get("modalities") or {}
        if modalities.get("vision"):
            out.add(Cap.VISION)
        if modalities.get("audio"):
            out.add(Cap.AUDIO_IN)
        template = str(payload.get("chat_template") or "")
        if "tool" in template.lower():
            out.add(Cap.TOOLS)
    except AttributeError:
        return frozenset()
    return frozenset(out)


def parse_lm_studio_models(payload: Mapping[str, Any], model_id) -> frozenset:
    """Map an LM Studio GET /api/v0/models entry onto Cap."""
    out = {Cap.CHAT, Cap.COMPLETION, Cap.STREAMING}
    try:
        for entry in payload.get("data") or ():
            if model_id and entry.get("id") != model_id:
                continue
            if entry.get("type") == "embeddings":
                out.add(Cap.EMBEDDINGS_ENDPOINT)
            if entry.get("vision"):
                out.add(Cap.VISION)
            if entry.get("tool_use") or entry.get("function_calling"):
                out.add(Cap.TOOLS)
    except AttributeError:
        return frozenset()
    return frozenset(out)


def parse_openai_models(payload: Mapping[str, Any]) -> tuple:
    """Extract model ids from an OpenAI-shaped {"data":[{"id":...}]} reply."""
    try:
        return tuple(
            str(e["id"]) for e in (payload.get("data") or ()) if isinstance(e, dict) and "id" in e
        )
    except AttributeError:
        return ()
