"""Single source of truth for optional-framework availability."""
import importlib.util
import importlib.metadata
import threading
from typing import Callable

_cache: dict[str, bool] = {}
_lock = threading.Lock()

def _ag2_probe() -> bool:
    # AG2 ships under the `autogen` namespace; presence of the dist is
    # the only reliable signal.
    try:
        importlib.metadata.distribution('ag2')
    except importlib.metadata.PackageNotFoundError:
        return False
    return importlib.util.find_spec("autogen") is not None

def _autogen_v4_probe() -> bool:
    return (importlib.util.find_spec("autogen_agentchat") is not None
            and importlib.util.find_spec("autogen_ext") is not None)

def _langgraph_probe() -> bool:
    # find_spec on a submodule imports the parent package; guard against
    # import-time errors in langgraph/its deps crashing the availability check.
    try:
        if importlib.util.find_spec("langgraph") is None:
            return False
        return importlib.util.find_spec("langgraph.prebuilt") is not None
    except Exception:
        return False

def _openai_agents_probe() -> bool:
    try:
        importlib.metadata.distribution("openai-agents")
    except importlib.metadata.PackageNotFoundError:
        return False
    if importlib.util.find_spec("agents") is None:
        return False
    try:
        from agents import Runner  # noqa: F401
        return True
    except ImportError:
        return False

def _agno_probe() -> bool:
    try:
        importlib.metadata.distribution("agno")
    except importlib.metadata.PackageNotFoundError:
        return False
    if importlib.util.find_spec("agno") is None:
        return False
    try:
        from agno.agent import Agent  # noqa: F401
        return True
    except ImportError:
        return False

def _google_adk_probe() -> bool:
    try:
        importlib.metadata.distribution("google-adk")
    except importlib.metadata.PackageNotFoundError:
        return False
    if importlib.util.find_spec("google.adk") is None:
        return False
    try:
        from google.adk.agents import Agent  # noqa: F401
        return True
    except ImportError:
        try:
            from google.adk import Agent  # noqa: F401
            return True
        except ImportError:
            return False

_PROBES: dict[str, Callable[[], bool]] = {
    "crewai":            lambda: importlib.util.find_spec("crewai") is not None,
    "autogen":           lambda: importlib.util.find_spec("autogen") is not None,
    "autogen_v4":        _autogen_v4_probe,
    "ag2":               _ag2_probe,
    "praisonaiagents":   lambda: importlib.util.find_spec("praisonaiagents") is not None,
    "praisonai_tools":   lambda: importlib.util.find_spec("praisonai_tools") is not None,
    "agentops":          lambda: importlib.util.find_spec("agentops") is not None,
    "litellm":           lambda: importlib.util.find_spec("litellm") is not None,
    "openai":            lambda: importlib.util.find_spec("openai") is not None,
    # Additional probes for Gap 2 consolidation
    "acp":               lambda: importlib.util.find_spec("acp") is not None,
    "rich":              lambda: importlib.util.find_spec("rich") is not None,
    "gradio":            lambda: importlib.util.find_spec("gradio") is not None,
    "unsloth":           lambda: importlib.util.find_spec("unsloth") is not None,
    # Vector store probes for Gap 3 fix
    "chromadb":          lambda: importlib.util.find_spec("chromadb") is not None,
    "pinecone":          lambda: importlib.util.find_spec("pinecone") is not None,
    "qdrant_client":     lambda: importlib.util.find_spec("qdrant_client") is not None,
    "weaviate":          lambda: importlib.util.find_spec("weaviate") is not None,
    "langgraph":         _langgraph_probe,
    "openai_agents":     _openai_agents_probe,
    "agno":              _agno_probe,
    "google_adk":        _google_adk_probe,
}

def is_available(name: str) -> bool:
    if name not in _PROBES:
        raise ValueError(f"unknown framework name: {name!r}")
    cached = _cache.get(name)
    if cached is not None:
        return cached
    with _lock:
        cached = _cache.get(name)
        if cached is None:
            cached = bool(_PROBES[name]())
            _cache[name] = cached
        return cached

def invalidate(name: str | None = None) -> None:
    with _lock:
        if name is None:
            _cache.clear()
        else:
            _cache.pop(name, None)