"""
Local OpenAI-compatible endpoint detection for keyless first runs.

Probes for a locally-reachable model server (e.g. Ollama) so a developer with
a model already running can `praisonai run "..."` before configuring any cloud
API key. Detection is timeout-bounded and negative results are cached briefly
so the credential hot path stays fast on every invocation.

This is a wrapper/first-run concern: the decision to probe localhost and treat
a running local endpoint as a zero-config default is CLI onboarding policy, not
agent-runtime behaviour.
"""

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

# Total time budget for a probe so the credential/first-run hot path is never
# stalled when nothing is listening. Kept small deliberately.
_PROBE_TIMEOUT_S = 0.15

# How long a negative probe is remembered so repeated invocations in the same
# process (e.g. bare TUI then run) don't re-pay the connection latency.
_NEGATIVE_CACHE_TTL_S = 30.0

# Default Ollama endpoint used when neither OPENAI_BASE_URL nor OLLAMA_HOST is
# set. Ollama exposes an OpenAI-compatible API under /v1.
_DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"

_DEFAULT_LOCAL_MODEL = "ollama/llama3.2"


@dataclass(frozen=True)
class LocalModel:
    """A detected local OpenAI-compatible endpoint."""
    model: str
    base_url: str


# Process-local cache: (monotonic_deadline, endpoint_key, result). ``result`` is
# ``None`` for a cached negative probe. ``endpoint_key`` pins the cache to the
# endpoint that produced it so a mid-process env change (OPENAI_BASE_URL /
# OLLAMA_HOST) is never served a stale result for a different server.
_cache: Optional[tuple[float, str, Optional[LocalModel]]] = None


def _root_host(host: str) -> str:
    """Return ``host`` without a trailing ``/v1`` (Ollama's native API root)."""
    host = host.rstrip("/")
    if host.endswith("/v1"):
        host = host[: -len("/v1")]
    return host.rstrip("/")


def _normalise_base(host: str) -> str:
    """Return an OpenAI-compatible base URL (``.../v1``) for ``host``."""
    host = host.rstrip("/")
    if host.endswith("/v1"):
        return host
    return host + "/v1"


def _candidate_host() -> str:
    """Resolve the host to probe, honouring env overrides."""
    base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OLLAMA_HOST")
    if base:
        # OLLAMA_HOST may be a bare host:port; give it a scheme.
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        return base
    return _DEFAULT_OLLAMA_HOST


def _get_json(url: str) -> Optional[dict]:
    """GET ``url`` and return decoded JSON, or ``None`` on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=_PROBE_TIMEOUT_S) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _probe_ollama_tags(host: str) -> Optional[str]:
    """Return the first model name from a reachable local endpoint, or ``None``.

    Probes Ollama's native ``/api/tags`` at the server *root* (so a base URL
    ending in ``/v1`` is not mangled into ``/v1/api/tags``). Falls back to the
    OpenAI-compatible ``/v1/models`` so a generic local server (llama.cpp,
    LM Studio, vLLM) that only speaks the OpenAI API is still detected.
    """
    root = _root_host(host)

    data = _get_json(root + "/api/tags")
    if data is not None:
        models = data.get("models")
        if isinstance(models, list) and models:
            name = models[0].get("name") if isinstance(models[0], dict) else None
            if isinstance(name, str) and name:
                return f"ollama/{name}"

    data = _get_json(_normalise_base(host) + "/models")
    if data is not None:
        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            model_id = first.get("id") if isinstance(first, dict) else None
            if isinstance(model_id, str) and model_id:
                # A generic OpenAI-compatible server (llama.cpp / LM Studio /
                # vLLM). Route it through the ``openai/`` provider against the
                # local base URL rather than mislabelling it as an Ollama model.
                return f"openai/{model_id}"

    return None


def detect_local_model(*, use_cache: bool = True) -> Optional[LocalModel]:
    """Detect a reachable local OpenAI-compatible endpoint.

    Checks ``OPENAI_BASE_URL`` / ``OLLAMA_HOST`` then ``127.0.0.1:11434``.
    Returns a :class:`LocalModel` (provider-prefixed model id + base URL) when a
    local server answers, otherwise ``None``. Negative results are cached for a
    short TTL so the hot path stays fast; pass ``use_cache=False`` to force a
    fresh probe.
    """
    global _cache

    host = _candidate_host()

    # Pin the cache to the resolved endpoint so a mid-process env change is never
    # served a stale positive/negative for a different server.
    if use_cache and _cache is not None:
        deadline, cached_key, cached = _cache
        if cached_key == host and time.monotonic() < deadline:
            return cached

    model_id = _probe_ollama_tags(host)

    result: Optional[LocalModel] = None
    if model_id:
        result = LocalModel(
            model=model_id,
            base_url=_normalise_base(host),
        )

    # Cache negatives briefly; a positive is stable enough to cache for the same
    # TTL (a server going away mid-session is rare and self-heals on expiry).
    _cache = (time.monotonic() + _NEGATIVE_CACHE_TTL_S, host, result)
    return result


def reset_cache() -> None:
    """Clear the probe cache (test hook)."""
    global _cache
    _cache = None
