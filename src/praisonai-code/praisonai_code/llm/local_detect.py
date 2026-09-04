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
from urllib.parse import urlsplit

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

# Ordered default candidates probed on the keyless first-run path when no env
# override is set. Ollama stays first so its behaviour is byte-for-byte
# unchanged; the rest are well-known local OpenAI-compatible runtimes on their
# default ports. First reachable wins, then probing short-circuits.
_DEFAULT_LOCAL_ENDPOINTS = (
    "http://127.0.0.1:11434",  # Ollama
    "http://127.0.0.1:1234",   # LM Studio
    "http://127.0.0.1:8000",   # vLLM
    "http://127.0.0.1:1337",   # Jan
    "http://127.0.0.1:8080",   # llama.cpp server
)

# Env override for the candidate list: a comma/whitespace separated list of
# host[:port] or full URLs (an explicit URL path prefix such as ``.../openai``
# is preserved and probed at ``<path>/v1/models``). Extends nothing — it
# replaces the defaults so a user can pin a non-standard host or narrow the set.
# Set to empty to disable probing.
_LOCAL_ENDPOINTS_ENV = "PRAISONAI_LOCAL_ENDPOINTS"


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


def _has_path_prefix(host: str) -> bool:
    """Return ``True`` if ``host`` is mounted under a non-``/v1`` URL path.

    Ollama's native ``/api/tags`` lives at the server root, so it is only
    meaningful for a bare host (optionally suffixed with ``/v1``). An endpoint
    mounted under an arbitrary path (e.g. ``http://host:8000/openai``) must be
    treated as OpenAI-compatible only and probed at ``<path>/v1/models`` — never
    at a rewritten ``<path>/api/tags`` root.
    """
    path = urlsplit(_with_scheme(host)).path.rstrip("/")
    return path not in ("", "/v1")


def _normalise_base(host: str) -> str:
    """Return an OpenAI-compatible base URL (``.../v1``) for ``host``."""
    host = host.rstrip("/")
    if host.endswith("/v1"):
        return host
    return host + "/v1"


def _with_scheme(host: str) -> str:
    """Return ``host`` with an ``http://`` scheme if it has none."""
    host = host.strip()
    if host and not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def _candidate_host() -> str:
    """Resolve an explicit override host to probe, or ``""`` if none is set."""
    base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OLLAMA_HOST")
    if base:
        # OLLAMA_HOST may be a bare host:port; give it a scheme.
        return _with_scheme(base)
    return ""


def _candidate_hosts() -> tuple[str, ...]:
    """Ordered list of hosts to probe on the keyless first-run path.

    ``OPENAI_BASE_URL`` / ``OLLAMA_HOST`` take precedence and are probed alone.
    Otherwise the ``PRAISONAI_LOCAL_ENDPOINTS`` env override (if set) replaces
    the built-in default list. An override set to an empty value disables
    probing entirely.
    """
    override_host = _candidate_host()
    if override_host:
        return (override_host,)

    raw = os.environ.get(_LOCAL_ENDPOINTS_ENV)
    if raw is not None:
        hosts = [
            _with_scheme(part)
            for part in raw.replace(",", " ").split()
            if part.strip()
        ]
        return tuple(hosts)

    return _DEFAULT_LOCAL_ENDPOINTS


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

    When ``host`` carries an explicit URL path prefix (e.g. ``.../openai``), the
    Ollama-native ``/api/tags`` probe is skipped — that path is preserved and
    only the OpenAI-compatible ``<path>/v1/models`` is consulted, so a runtime
    mounted beneath an arbitrary path is detected and its base URL kept intact.
    """
    if not _has_path_prefix(host):
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

    Honours ``OPENAI_BASE_URL`` / ``OLLAMA_HOST`` first, then the
    ``PRAISONAI_LOCAL_ENDPOINTS`` override, then a built-in ordered list of
    well-known local runtimes (Ollama, LM Studio, vLLM, Jan, llama.cpp). The
    first reachable endpoint wins. Returns a :class:`LocalModel`
    (provider-prefixed model id + base URL) when a local server answers,
    otherwise ``None``. Results are cached for a short TTL so the hot path stays
    fast; pass ``use_cache=False`` to force a fresh probe.
    """
    global _cache

    hosts = _candidate_hosts()

    # Pin the cache to the resolved candidate set so a mid-process env change is
    # never served a stale positive/negative for a different server.
    cache_key = "|".join(hosts)
    if use_cache and _cache is not None:
        deadline, cached_key, cached = _cache
        if cached_key == cache_key and time.monotonic() < deadline:
            return cached

    result: Optional[LocalModel] = None
    for host in hosts:
        model_id = _probe_ollama_tags(host)
        if model_id:
            result = LocalModel(
                model=model_id,
                base_url=_normalise_base(host),
            )
            break

    # Cache negatives briefly; a positive is stable enough to cache for the same
    # TTL (a server going away mid-session is rare and self-heals on expiry).
    _cache = (time.monotonic() + _NEGATIVE_CACHE_TTL_S, cache_key, result)
    return result


def reset_cache() -> None:
    """Clear the probe cache (test hook)."""
    global _cache
    _cache = None
