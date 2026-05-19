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