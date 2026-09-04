"""Identify which local model server is listening, without inferring from the port.

Port collisions are real: 8080 is claimed by llama-server, mlx_lm, llamafile,
LocalAI and RamaLama; 8000 by vLLM and `transformers serve`. Identity is therefore
never inferred from a port -- a ProbeSpec matches only when every Rule holds, and
RuleKind.ABSENT rules exist specifically to separate co-tenants of one port.

Standard library only. urllib.request rather than httpx: httpx is present only as
an undeclared transitive dependency of `openai`, and a package whose whole point
is that anything can import it must not rest on that.
"""

from __future__ import annotations

import concurrent.futures
import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from .capabilities import ApiStyle, Evidence, LocalEngine, parse_openai_models
from .errors import InvalidLocalSpecError

__all__ = [
    "HttpReply", "RuleKind", "Rule", "ProbeSpec", "Discovery",
    "PROBES", "LOOPBACK_HOST", "DEFAULT_PROBE_TIMEOUT", "DEFAULT_TOTAL_BUDGET",
    "probe_table", "probe_endpoint", "discover", "models", "default_transport",
]

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PROBE_TIMEOUT = 0.4
DEFAULT_TOTAL_BUDGET = 1.5
_MAX_BODY = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class HttpReply:
    status: int                 # 0 == transport failure
    body: bytes = b""
    error: Optional[str] = None  # "refused" | "timeout" | "reset" | "http" | None


class RuleKind(str, Enum):
    BODY_PREFIX = "body_prefix"
    JSON_KEY = "json_key"
    STATUS_OK = "status_ok"
    ABSENT = "absent"


@dataclass(frozen=True)
class Rule:
    method: str
    path: str
    kind: RuleKind
    value: str = ""


@dataclass(frozen=True)
class ProbeSpec:
    engine: LocalEngine
    default_ports: tuple
    identity: tuple
    api_style: ApiStyle
    verified: bool
    note: str
    version_path: Optional[str] = None
    version_key: Optional[str] = None
    models_path: Optional[str] = None
    models_key: Optional[str] = None
    model_caps: Optional[Rule] = None


@dataclass(frozen=True)
class Discovery:
    engine: LocalEngine
    base_url: str
    api_style: ApiStyle
    evidence: Evidence
    engine_version: Optional[str] = None
    models: tuple = ()
    # Per-model metadata when the server offers it, as a tuple of
    # (model_id, capabilities_tuple, modified_at) -- enough to choose a model
    # without a second request. Empty when the server reports names only.
    model_meta: tuple = ()
    raw_identity: str = ""
    latency_ms: int = 0
    blocked: Optional[str] = None


PROBES: tuple = (
    ProbeSpec(
        engine=LocalEngine.OLLAMA,
        default_ports=(11434,),
        identity=(Rule("GET", "/", RuleKind.BODY_PREFIX, "Ollama is running"),),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=True,
        note=("verified 0.33.2 @ 2026-09-03: GET / -> 'Ollama is running'; "
              "/api/version -> {'version':'0.33.2'}; /api/tags entries carry "
              "capabilities and modified_at; POST /api/show carries capabilities."),
        version_path="/api/version", version_key="version",
        models_path="/api/tags", models_key="models[].model",
        model_caps=Rule("POST", "/api/show", RuleKind.JSON_KEY, "capabilities"),
    ),
    ProbeSpec(
        engine=LocalEngine.LLAMA_CPP,
        default_ports=(8080,),
        identity=(Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/props", RuleKind.JSON_KEY, "build_info")),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note=("binary present (build 7620), --port default 8080 confirmed from "
              "--help; /props reply shape NOT re-verified live."),
        version_path="/props", version_key="build_info",
        models_path="/v1/models", models_key="data[].id",
        model_caps=Rule("GET", "/props", RuleKind.JSON_KEY, "modalities"),
    ),
    ProbeSpec(
        engine=LocalEngine.MLX_LM,
        default_ports=(8080,),
        identity=(Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/props", RuleKind.ABSENT),
                  Rule("GET", "/v1/models", RuleKind.JSON_KEY, "data")),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note=("mlx_lm.server present on PATH; default port 8080. Identity is "
              "'/health answers AND /props does not', to separate it from "
              "llama.cpp on the same port."),
        models_path="/v1/models", models_key="data[].id",
    ),
    ProbeSpec(
        engine=LocalEngine.LM_STUDIO,
        default_ports=(1234,),
        identity=(Rule("GET", "/api/v0/models", RuleKind.JSON_KEY, "data"),),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note=("LM Studio not installed on the machine this was written on. "
              "/api/v0/models is richer than /v1/models and is the discriminator. "
              "Use HTTP, not the Python SDK (stale since Aug 2025, WebSocket-based)."),
        models_path="/api/v0/models", models_key="data[].id",
        model_caps=Rule("GET", "/api/v0/models", RuleKind.JSON_KEY, "data"),
    ),
    ProbeSpec(
        engine=LocalEngine.VLLM,
        default_ports=(8000,),
        identity=(Rule("GET", "/version", RuleKind.JSON_KEY, "version"),),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note=("Linux only. Tools require BOTH --enable-auto-tool-choice AND "
              "--tool-call-parser, else tool calls come back as plain text."),
        version_path="/version", version_key="version",
        models_path="/v1/models", models_key="data[].id",
    ),
    ProbeSpec(
        engine=LocalEngine.TRANSFORMERS_SERVE,
        default_ports=(8000,),
        identity=(Rule("GET", "/version", RuleKind.ABSENT),
                  Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/v1/models", RuleKind.JSON_KEY, "data")),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note=("`transformers serve`, default 8000; /health is undocumented. "
              "Identity is '/version absent AND /health ok', to separate it "
              "from vLLM on 8000."),
        models_path="/v1/models", models_key="data[].id",
    ),
)


def probe_table() -> tuple:
    """The ordered probe table (identity endpoints and discriminators)."""
    return PROBES


def default_transport(method: str, url: str, body, timeout: float) -> HttpReply:
    """The only thing in this package that touches a socket."""
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "praisonaiagents-local/1")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpReply(resp.status, resp.read(_MAX_BODY))
    except urllib.error.HTTPError as exc:
        # HTTPError is both an exception and a response: read it, don't leak it.
        try:
            payload = exc.read(_MAX_BODY)
        except Exception:
            payload = b""
        return HttpReply(exc.code, payload, "http")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout) or isinstance(reason, TimeoutError):
            return HttpReply(0, b"", "timeout")
        return HttpReply(0, b"", "refused")
    except (socket.timeout, TimeoutError):
        return HttpReply(0, b"", "timeout")
    except ConnectionResetError:
        return HttpReply(0, b"", "reset")
    except (OSError, ValueError, http.client.HTTPException):
        return HttpReply(0, b"", "refused")


def _json(reply: HttpReply):
    try:
        return json.loads(reply.body.decode("utf-8", errors="replace"))
    except (ValueError, AttributeError):
        return None


def _rule_holds(rule: Rule, reply: HttpReply) -> bool:
    if rule.kind is RuleKind.ABSENT:
        if reply.status in (404, 405):
            return True
        if reply.status == 0:
            return False
        return _json(reply) is None
    if rule.kind is RuleKind.STATUS_OK:
        return 200 <= reply.status < 300
    if reply.status != 200:
        return False
    if rule.kind is RuleKind.BODY_PREFIX:
        return reply.body.decode("utf-8", errors="replace").lstrip().startswith(rule.value)
    if rule.kind is RuleKind.JSON_KEY:
        obj = _json(reply)
        return isinstance(obj, dict) and rule.value in obj
    return False


def _extract_model_meta(payload, key) -> tuple:
    """Per-model (id, capabilities, modified_at) when the listing carries it."""
    if key != "models[].model" or not isinstance(payload, dict):
        return ()
    out = []
    for m in payload.get("models") or ():
        if isinstance(m, dict) and "model" in m:
            caps = tuple(str(c).lower() for c in (m.get("capabilities") or ()))
            out.append((str(m["model"]), caps, str(m.get("modified_at") or "")))
    return tuple(out)


def _extract_models(payload, key) -> tuple:
    if not isinstance(payload, dict) or not key:
        return ()
    if key == "data[].id":
        return parse_openai_models(payload)
    if key == "models[].model":
        return tuple(
            str(m["model"]) for m in (payload.get("models") or ())
            if isinstance(m, dict) and "model" in m
        )
    return ()


def probe_endpoint(base_url: str, *, expect=None, timeout: float = DEFAULT_PROBE_TIMEOUT,
                   transport=None) -> Optional[Discovery]:
    """Identify the server at ``base_url``, or None if nothing identifiable answered.

    A 200 that matches no discriminator yields engine=UNKNOWN. A bodyless 403
    yields blocked="host_header_rejected" rather than being reported as absent.
    """
    base = (base_url or "").rstrip("/")
    if "://" not in base or not base.split("://", 1)[1]:
        raise InvalidLocalSpecError(f"Not a usable base URL: {base_url!r}")
    send = transport or default_transport
    started = time.monotonic()

    candidates = [p for p in PROBES if expect is None or p.engine == LocalEngine(expect)]
    cache = {}

    def fetch(method, path, body=None):
        key = (method, path)
        if key not in cache:
            cache[key] = send(method, base + path, body, timeout)
        return cache[key]

    first_reply = None
    for spec in candidates:
        ok = True
        for rule in spec.identity:
            reply = fetch(rule.method, rule.path,
                          b'{"model":""}' if rule.method == "POST" else None)
            if first_reply is None:
                first_reply = reply
            if reply.status in (401, 403) and not reply.body:
                return Discovery(
                    engine=LocalEngine(expect) if expect else LocalEngine.UNKNOWN,
                    base_url=base, api_style=spec.api_style, evidence=Evidence.TABLE,
                    blocked="host_header_rejected",
                    latency_ms=int((time.monotonic() - started) * 1000))
            if not _rule_holds(rule, reply):
                ok = False
                break
        if not ok:
            continue
        version = None
        if spec.version_path:
            obj = _json(fetch("GET", spec.version_path))
            if isinstance(obj, dict) and spec.version_key:
                v = obj.get(spec.version_key)
                version = str(v) if v is not None else None
        found, meta = (), ()
        if spec.models_path:
            listing = _json(fetch("GET", spec.models_path))
            found = _extract_models(listing, spec.models_key)
            meta = _extract_model_meta(listing, spec.models_key)
        raw = b""
        if spec.identity:
            raw = fetch(spec.identity[0].method, spec.identity[0].path).body
        return Discovery(
            engine=spec.engine, base_url=base, api_style=spec.api_style,
            evidence=Evidence.SERVER, engine_version=version, models=found,
            model_meta=meta,
            raw_identity=raw.decode("utf-8", errors="replace")[:200],
            latency_ms=int((time.monotonic() - started) * 1000))

    # Something answered but matched no discriminator: report it honestly.
    if first_reply is not None and first_reply.status == 200:
        listing = _json(fetch("GET", "/v1/models"))
        return Discovery(
            engine=LocalEngine.UNKNOWN, base_url=base,
            api_style=ApiStyle.OPENAI_CHAT if isinstance(listing, dict) else ApiStyle.OPENAI_COMPLETIONS,
            evidence=Evidence.TABLE,
            models=parse_openai_models(listing) if isinstance(listing, dict) else (),
            raw_identity=first_reply.body.decode("utf-8", errors="replace")[:200],
            latency_ms=int((time.monotonic() - started) * 1000))
    return None


def discover(*, ports: Optional[Sequence] = None, include: Optional[Sequence] = None,
             host: str = LOOPBACK_HOST, timeout: float = DEFAULT_PROBE_TIMEOUT,
             budget: float = DEFAULT_TOTAL_BUDGET, transport=None) -> tuple:
    """Scan the probe table's default ports; return every server found.

    Ports are probed concurrently. Results are ordered by PROBES order then port,
    so Ollama on 11434 outranks an unidentified server on 8000. Never raises.
    """
    wanted = [p for p in PROBES if include is None or p.engine in {LocalEngine(e) for e in include}]
    targets = []
    for spec in wanted:
        for port in (ports if ports is not None else spec.default_ports):
            targets.append((spec.engine, port))
    seen_ports = sorted({p for _, p in targets})

    results = {}
    deadline = time.monotonic() + budget

    def work(port):
        if time.monotonic() > deadline:
            return port, None
        try:
            return port, probe_endpoint(f"http://{host}:{port}", timeout=timeout,
                                        transport=transport)
        except Exception:
            return port, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for port, found in pool.map(work, seen_ports):
            if found is not None:
                results[port] = found

    ordered = []
    for spec in wanted:
        for port in (ports if ports is not None else spec.default_ports):
            found = results.get(port)
            if found is not None and found.engine == spec.engine and found not in ordered:
                ordered.append(found)
    for found in results.values():
        if found not in ordered:
            ordered.append(found)
    return tuple(ordered)


def models(discovery: Discovery, *, timeout: float = DEFAULT_PROBE_TIMEOUT,
           transport=None) -> tuple:
    """List model ids served at ``discovery.base_url`` (GET only). Never raises."""
    spec = next((p for p in PROBES if p.engine == discovery.engine), None)
    if spec is None or not spec.models_path:
        return discovery.models
    send = transport or default_transport
    reply = send("GET", discovery.base_url + spec.models_path, None, timeout)
    return _extract_models(_json(reply), spec.models_key) or discovery.models
