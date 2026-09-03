"""Resolution precedence and the process-local cache.

Precedence: spec > PRAISONAI_LOCAL_BASE_URL > OLLAMA_HOST >
OPENAI_BASE_URL/OPENAI_API_BASE (only when local) > probe-table scan.

The first three are authoritative: if one names a server that does not answer
this raises, rather than silently talking to a different one. Silently using a
server the caller did not name is the failure mode this package exists to
prevent.
"""

from __future__ import annotations

import ipaddress
import os
import threading
import time
import urllib.parse

from .capabilities import Cap, Evidence, LocalEngine, default_caps
from .capabilities import (parse_llama_cpp_props, parse_lm_studio_models,
                           parse_ollama_capabilities)
from .discover import (DEFAULT_PROBE_TIMEOUT, DEFAULT_TOTAL_BUDGET, PROBES,
                       default_transport, discover, probe_endpoint)
from .errors import (EngineUnreachableError, HostHeaderRejectedError,
                     InvalidLocalSpecError, LocalError, ModelNotAvailableError,
                     NoLocalEngineError)
from .target import (ENV_BASE_URL, ENV_ENGINE, ENV_MODEL, build_target,
                     parse_ollama_host, parse_spec, select_model)

ENV_TTL = "PRAISONAI_LOCAL_TTL"
ENV_NEG_TTL = "PRAISONAI_LOCAL_NEG_TTL"
ENV_TIMEOUT = "PRAISONAI_LOCAL_TIMEOUT"

__all__ = ["resolve", "resolve_or_none", "clear_cache", "cache_info",
           "ENV_TTL", "ENV_NEG_TTL", "ENV_TIMEOUT"]

def _is_local_host(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    if host in ("localhost", "") or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def _model_capabilities(discovery: Discovery, model_id, *, timeout, transport):
    """One request, at most, for per-model capabilities. Degrades to TABLE."""
    spec = next((p for p in PROBES if p.engine == discovery.engine), None)
    if spec is None or spec.model_caps is None or not model_id:
        return default_caps(discovery.engine), Evidence.TABLE, ()
    send = transport or default_transport
    rule = spec.model_caps
    import json as _json
    body = _json.dumps({"model": model_id}).encode() if rule.method == "POST" else None
    reply = send(rule.method, discovery.base_url + rule.path, body, timeout)
    if reply.status != 200:
        return default_caps(discovery.engine), Evidence.TABLE, ()
    try:
        payload = _json.loads(reply.body.decode("utf-8", errors="replace"))
    except ValueError:
        return default_caps(discovery.engine), Evidence.TABLE, ()
    if not isinstance(payload, dict):
        return default_caps(discovery.engine), Evidence.TABLE, ()

    if discovery.engine == LocalEngine.OLLAMA:
        caps = parse_ollama_capabilities(payload)
    elif discovery.engine == LocalEngine.LLAMA_CPP:
        caps = parse_llama_cpp_props(payload)
    elif discovery.engine == LocalEngine.LM_STUDIO:
        caps = parse_lm_studio_models(payload, model_id)
    else:
        caps = frozenset()
    if not caps:
        return default_caps(discovery.engine), Evidence.TABLE, ()

    extra = []
    info = payload.get("model_info") or {}
    if isinstance(info, dict):
        for key, value in info.items():
            if key.endswith(".context_length"):
                extra.append(("context_length", str(value)))
            elif key.endswith(".embedding_length"):
                extra.append(("embedding_length", str(value)))
    details = payload.get("details") or {}
    if isinstance(details, dict):
        for k in ("family", "parameter_size", "quantization_level"):
            if details.get(k):
                extra.append((k, str(details[k])))
    # Union with the engine floor so streaming/embeddings survive.
    return frozenset(caps) | default_caps(discovery.engine), Evidence.SERVER, tuple(extra)


_CACHE_LOCK = threading.Lock()
_TARGETS = {}
_NEGATIVES = {}
_STATS = {"hits": 0, "misses": 0}


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _cache_key(spec, timeout):
    return "\x00".join((
        str(spec) if spec is not None else "*",
        os.environ.get(ENV_BASE_URL, ""), os.environ.get(ENV_ENGINE, ""),
        os.environ.get(ENV_MODEL, ""), os.environ.get("OLLAMA_HOST", ""),
        os.environ.get("OPENAI_BASE_URL", ""), os.environ.get("OPENAI_API_BASE", ""),
        f"{timeout:.3f}",
    ))


def clear_cache() -> None:
    """Drop every cached target and negative result (test hook)."""
    with _CACHE_LOCK:
        _TARGETS.clear()
        _NEGATIVES.clear()
        _STATS.update(hits=0, misses=0)


def cache_info() -> dict:
    with _CACHE_LOCK:
        return {"targets": len(_TARGETS), "negatives": len(_NEGATIVES), **_STATS}


_ERRORS = {c.__name__: c for c in (
    NoLocalEngineError, EngineUnreachableError, HostHeaderRejectedError,
    ModelNotAvailableError, InvalidLocalSpecError, LocalError)}


def resolve(spec=None, *, timeout=None, refresh=False, transport=None) -> LocalTarget:
    """Resolve the local model server and model this machine should use.

    Precedence: spec > PRAISONAI_LOCAL_BASE_URL > OLLAMA_HOST >
    OPENAI_BASE_URL/OPENAI_API_BASE (only when local) > probe-table scan.

    The first three are authoritative: if one names a server that does not
    answer, this raises rather than silently talking to a different one.
    """
    total = _float_env(ENV_TIMEOUT, 1.5) if timeout is None else float(timeout)
    total = min(max(total, 0.05), 30.0)
    per_request = min(DEFAULT_PROBE_TIMEOUT, total / 3)
    key = _cache_key(spec, total)
    pid = os.getpid()

    if not refresh:
        with _CACHE_LOCK:
            hit = _TARGETS.get(key)
            if hit and hit[0] > time.monotonic() and hit[1] == pid:
                _STATS["hits"] += 1
                return hit[2]
            neg = _NEGATIVES.get(key)
            if neg and neg[0] > time.monotonic() and neg[1] == pid:
                _STATS["hits"] += 1
                # A fresh instance: a stored exception carries a dead traceback.
                raise _ERRORS.get(neg[2], LocalError)(neg[3])
    with _CACHE_LOCK:
        _STATS["misses"] += 1

    try:
        target = _resolve_uncached(spec, per_request, total, transport)
    except LocalError as exc:
        ttl = _float_env(ENV_NEG_TTL, 5.0)
        if ttl > 0:
            with _CACHE_LOCK:
                _NEGATIVES[key] = (time.monotonic() + ttl, pid, type(exc).__name__, str(exc))
        raise
    ttl = _float_env(ENV_TTL, 30.0)
    if ttl > 0:
        with _CACHE_LOCK:
            _TARGETS[key] = (time.monotonic() + ttl, pid, target)
    return target


def _with_url_evidence(discovery, evidence):
    """Record where the base URL came from; the probe only proves it answered."""
    import dataclasses
    return dataclasses.replace(discovery, evidence=evidence) if evidence else discovery


def _require_model(discovery, model_id):
    """Reject a model-less resolution or a named model the server does not serve."""
    available = tuple(discovery.models)
    where = f"{discovery.engine.value} at {discovery.base_url}"
    if model_id is None:
        raise NoLocalEngineError(
            f"{where} answered but lists no usable model to chat with. Pull one "
            f"(e.g. `ollama pull qwen3:0.6b`) or name it explicitly.")
    if available and model_id not in available:
        raise ModelNotAvailableError(
            f"Model {model_id!r} is not served by {where}. "
            f"Available: {', '.join(available)}.",
            model_id=model_id, available=available)


def _finish(discovery, model_id, model_evidence, per_request, transport, url_evidence=None):
    if model_id is None:
        model_id = select_model(discovery, transport=transport, timeout=per_request)
        model_evidence = Evidence.SERVER
    # An explicitly named model must be served, and a reachable server that
    # lists none must not yield a model-less target -- Agent would otherwise
    # substitute its own default (e.g. gpt-4o-mini) and send it to the local
    # endpoint, failing only on the first completion instead of at resolution.
    _require_model(discovery, model_id)
    caps, caps_evidence, extra = _model_capabilities(
        discovery, model_id, timeout=per_request, transport=transport)
    target = build_target(discovery, model_id, caps=caps, caps_evidence=caps_evidence,
                          model_evidence=model_evidence, extra=extra)
    if url_evidence is not None:
        import dataclasses
        ev = dict(target.evidence)
        ev["base_url"] = url_evidence
        target = dataclasses.replace(target, evidence=tuple(sorted(ev.items())))
    return target


def _authoritative(url, expect, source, per_request, transport, model_id, model_evidence):
    found = probe_endpoint(url, expect=expect, timeout=per_request, transport=transport)
    if found is None:
        hint = ""
        if source == "OLLAMA_HOST" and url.rsplit(":", 1)[-1] in ("80", "443"):
            hint = (" Note that OLLAMA_HOST with an explicit http:// scheme and no "
                    "port means port 80, not 11434.")
        raise EngineUnreachableError(
            f"Local runtime at {url} did not answer (refused). It was named "
            f"explicitly by {source}, so no other port was probed.{hint}",
            base_url=url, reason="refused", source=source)
    if found.blocked:
        raise HostHeaderRejectedError(
            f"Local runtime at {url} returned HTTP 403 with an empty body. Ollama "
            f"rejects any request whose Host header is not localhost or an IP "
            f"address; set OLLAMA_HOST on the server to allow this origin.",
            base_url=url, reason="http_403", source=source)
    return found, model_id, model_evidence


def _resolve_uncached(spec, per_request, total, transport):
    engine, spec_url, spec_model = parse_spec(spec)
    model_evidence = Evidence.SPEC if spec_model else Evidence.SERVER

    if spec_url:
        found, m, ev = _authoritative(spec_url, engine, "spec", per_request,
                                      transport, spec_model, model_evidence)
        return _finish(found, m, ev, per_request, transport, Evidence.SPEC)

    env_url = os.environ.get(ENV_BASE_URL)
    if env_url:
        env_engine = os.environ.get(ENV_ENGINE)
        expect = engine
        if env_engine:
            try:
                expect = LocalEngine(env_engine.lower())
            except ValueError:
                raise InvalidLocalSpecError(
                    f"{ENV_ENGINE}={env_engine!r} is not a known local engine. "
                    f"Expected one of: {', '.join(e.value for e in LocalEngine)}.")
        found, m, ev = _authoritative(env_url.rstrip("/"), expect, ENV_BASE_URL,
                                      per_request, transport, spec_model, model_evidence)
        return _finish(found, m, ev, per_request, transport, Evidence.ENV)

    ollama_host = os.environ.get("OLLAMA_HOST")
    if ollama_host:
        url = parse_ollama_host(ollama_host)
        if url:
            found, m, ev = _authoritative(url, engine or LocalEngine.OLLAMA, "OLLAMA_HOST",
                                          per_request, transport, spec_model, model_evidence)
            return _finish(found, m, ev, per_request, transport, Evidence.ENV)

    skipped = ""
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        url = os.environ.get(var)
        if not url:
            continue
        if not _is_local_host(url):
            skipped = f" Ignored {var}={url!r}: not a local address."
            continue
        found = probe_endpoint(url.rstrip("/"), expect=engine, timeout=per_request,
                               transport=transport)
        if found is not None and not found.blocked:
            return _finish(found, spec_model, model_evidence, per_request, transport)

    include = [engine] if engine else None
    results = discover(include=include, timeout=per_request, budget=total,
                       transport=transport)
    usable = [d for d in results if not d.blocked]
    if usable:
        return _finish(usable[0], spec_model, model_evidence, per_request, transport)
    if results:
        blocked = results[0]
        raise HostHeaderRejectedError(
            f"Local runtime at {blocked.base_url} returned HTTP 403 with an empty "
            f"body. Ollama rejects any request whose Host header is not localhost "
            f"or an IP address; set OLLAMA_HOST on the server to allow this origin.",
            base_url=blocked.base_url, reason="http_403", source="scan")

    ports = {}
    for p in PROBES:
        for port in p.default_ports:
            ports.setdefault(port, []).append(p.engine.value)
    clause = ", ".join(f"{port} ({', '.join(names)})" for port, names in sorted(ports.items()))
    raise NoLocalEngineError(
        f"No local model runtime found. Probed {DEFAULT_TOTAL_BUDGET and '127.0.0.1'} "
        f"ports {clause} in {total:.1f}s; nothing answered. Start one "
        f"(e.g. `ollama serve`, then `ollama pull qwen3:0.6b`) or set "
        f"{ENV_BASE_URL} to its address.{skipped}")


def resolve_or_none(spec=None, **kwargs):
    """resolve() but returns None instead of raising LocalError."""
    try:
        return resolve(spec, **kwargs)
    except LocalError:
        return None
