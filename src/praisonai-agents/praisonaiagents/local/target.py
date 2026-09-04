"""The LocalTarget value type and the pure helpers that build one.

Everything here is a pure function of its arguments: no network, no cache, no
environment reads except the single documented model override. Resolution
precedence lives in resolve.py.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

from .capabilities import (ApiStyle, Cap, Evidence, LocalEngine, default_caps,
                           parse_llama_cpp_props, parse_lm_studio_models,
                           parse_ollama_capabilities)
from .discover import (DEFAULT_PROBE_TIMEOUT, DEFAULT_TOTAL_BUDGET, PROBES,
                       Discovery, default_transport, discover, probe_endpoint)
from .errors import InvalidLocalSpecError, ModelNotAvailableError
from .quirktable import Quirk, quirks_for

__all__ = ["LocalTarget", "build_target", "litellm_model_for", "parse_spec",
           "parse_ollama_host", "select_model", "DEFAULT_API_KEY",
           "ENV_BASE_URL", "ENV_ENGINE", "ENV_MODEL"]

DEFAULT_API_KEY = "local"
ENV_BASE_URL = "PRAISONAI_LOCAL_BASE_URL"
ENV_ENGINE = "PRAISONAI_LOCAL_ENGINE"
ENV_MODEL = "PRAISONAI_LOCAL_MODEL"


@dataclass(frozen=True)
class LocalTarget:
    engine: LocalEngine
    base_url: str
    openai_base_url: str
    api_style: ApiStyle
    model_id: Optional[str]
    caps: frozenset
    quirks: frozenset
    litellm_model: Optional[str]
    api_key: str
    engine_version: Optional[str]
    # Tuples of pairs, not dicts: a dict field would make the generated __hash__
    # raise TypeError at runtime, and this type is meant to be hashable.
    evidence: tuple
    extra: tuple
    probed_at: float

    def supports(self, cap) -> bool:
        return Cap(cap) in self.caps

    def has_quirk(self, quirk) -> bool:
        return Quirk(quirk) in self.quirks

    def evidence_for(self, field: str) -> Evidence:
        return dict(self.evidence).get(field, Evidence.UNKNOWN)

    def get_extra(self, key: str, default=None):
        return dict(self.extra).get(key, default)

    def as_dict(self) -> dict:
        return {
            "engine": self.engine.value,
            "base_url": self.base_url,
            "openai_base_url": self.openai_base_url,
            "api_style": self.api_style.value,
            "model_id": self.model_id,
            "caps": sorted(c.value for c in self.caps),
            "quirks": sorted(q.value for q in self.quirks),
            "litellm_model": self.litellm_model,
            "engine_version": self.engine_version,
            "evidence": {k: v.value for k, v in self.evidence},
            "extra": dict(self.extra),
        }


_LITELLM_PREFIX = {
    LocalEngine.OLLAMA: "ollama",
    LocalEngine.LM_STUDIO: "lm_studio",
    LocalEngine.VLLM: "hosted_vllm",
}


def litellm_model_for(engine, model_id) -> Optional[str]:
    """Format a litellm model string for this engine. Pure.

    OLLAMA maps to "ollama/", never "ollama_chat/": llm.py's _detect_provider
    resolves ollama_chat to "openai" and would silently lose OllamaAdapter.
    """
    if not model_id:
        return None
    return f"{_LITELLM_PREFIX.get(LocalEngine(engine), 'openai')}/{model_id}"


def parse_ollama_host(value: str) -> Optional[str]:
    """Apply Ollama's own OLLAMA_HOST rules and return a base_url.

    The asymmetry that catches people: a bare host defaults to port 11434, but an
    explicit http:// with no port means port 80 -- not 11434.
    """
    if not value or not value.strip():
        return None
    raw = value.strip()
    if "://" in raw:
        parsed = urllib.parse.urlparse(raw)
        if not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{parsed.scheme}://{parsed.hostname}:{port}"
    if raw.isdigit():
        return f"http://127.0.0.1:{raw}"
    if raw.startswith(":") and raw[1:].isdigit():
        return f"http://127.0.0.1:{raw[1:]}"
    if raw.count(":") > 1 and not raw.startswith("["):
        return None  # unbracketed IPv6
    host, _, port = raw.partition(":")
    return f"http://{host}:{port or 11434}"




def parse_spec(spec):
    """Split a spec into (engine, base_url, model_id); any element may be None."""
    if spec is None:
        return None, None, None
    text = str(spec).strip()
    if text.lower() in ("", "local", "auto"):
        return None, None, None
    if "://" in text:
        url, _, fragment = text.partition("#")
        return None, url.rstrip("/"), (fragment or None)
    if "/" in text:
        head, _, tail = text.partition("/")
        try:
            return LocalEngine(head.lower()), None, (tail or None)
        except ValueError:
            pass
    raise InvalidLocalSpecError(
        f"Cannot parse local spec {spec!r}. Expected None, 'local', "
        f"'<engine>/<model>', a base URL, or '<url>#<model>'."
    )


def select_model(discovery: Discovery, *, transport=None,
                 timeout: float = DEFAULT_PROBE_TIMEOUT) -> Optional[str]:
    """Pick a model deterministically when the caller named none.

    Never guesses a model that is not in the server's list.
    """
    named = os.environ.get(ENV_MODEL)
    available = tuple(discovery.models)
    if named:
        if available and named not in available:
            raise ModelNotAvailableError(
                f"Model {named!r} is not served by {discovery.engine.value} at "
                f"{discovery.base_url}. Available: {', '.join(available) or '(none)'}.",
                model_id=named, available=available)
        return named
    if not available:
        return None
    meta = {m[0]: (m[1], m[2]) for m in (discovery.model_meta or ())}
    if len(available) == 1 and not meta:
        return available[0]

    def rank(model):
        caps, modified = meta.get(model, ((), ""))
        # An embedding-only model cannot hold a conversation. Picking one because
        # it sorted first is the kind of silent nonsense this package exists to
        # prevent, so it is ranked last rather than merely unpreferred.
        embed_only = bool(caps) and "embedding" in caps and "completion" not in caps
        return (embed_only, "tools" not in caps, _negate_iso(modified), model)

    chat_capable = [m for m in available if not rank(m)[0]]
    pool = chat_capable or list(available)
    return sorted(pool, key=rank)[0]


def _negate_iso(value: str):
    """Sort ISO-8601 timestamps newest-first inside an ascending sort key."""
    return tuple(-ord(c) for c in value) if value else ()


def build_target(discovery: Discovery, model_id, *, caps=None,
                 caps_evidence=Evidence.TABLE, model_evidence=Evidence.SERVER,
                 extra=()) -> LocalTarget:
    """Assemble a LocalTarget from a Discovery. Pure: no network, no cache."""
    engine = discovery.engine
    resolved_caps = frozenset(caps) if caps is not None else default_caps(engine)
    quirks = quirks_for(engine, discovery.api_style, caps=resolved_caps)
    if Cap.TOOLS in resolved_caps and Quirk.TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL not in quirks:
        resolved_caps = resolved_caps | {Cap.STREAMING_WITH_TOOLS}
    evidence = {
        "engine": discovery.evidence,
        "base_url": discovery.evidence,
        "api_style": Evidence.TABLE,
        "caps": caps_evidence,
        "quirks": Evidence.TABLE,
        "model_id": model_evidence if model_id else Evidence.UNKNOWN,
        "engine_version": Evidence.SERVER if discovery.engine_version else Evidence.UNKNOWN,
    }
    return LocalTarget(
        engine=engine,
        base_url=discovery.base_url,
        openai_base_url=discovery.base_url + "/v1",
        api_style=discovery.api_style,
        model_id=model_id,
        caps=resolved_caps,
        quirks=quirks,
        litellm_model=litellm_model_for(engine, model_id),
        api_key=DEFAULT_API_KEY,
        engine_version=discovery.engine_version,
        evidence=tuple(sorted(evidence.items())),
        extra=tuple(sorted(extra)),
        probed_at=time.time(),
    )
