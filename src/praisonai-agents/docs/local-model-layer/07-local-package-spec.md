# 07 — `praisonaiagents/local/` API specification

**Branch:** `feat/local-model-resolver`
**Status:** normative specification. No implementation exists yet.
**Owns:** `praisonaiagents/local/**` (new), `src/praisonai/tests/unit/llm/local/**` (new).
Touches nothing else. Tests live under `src/praisonai/tests/` — **not** `src/praisonai-agents/tests/` —
because CI runs `cd src/praisonai && pytest tests/unit/` and collects nothing from the
agents-package tree (see `00-ground-truth.md`). Tests placed there run nowhere, so the
import-boundary and no-socket guards below would silently never execute.
**Verified on:** 2026-09-03, macOS (Darwin 27.0.0), Ollama 0.33.2 live on `127.0.0.1:11434`,
`llama-server` build 7620 present, `mlx_lm.server` present.

An implementing agent may implement **one module in isolation** by reading only §2
(constraints), §4 (layering), and that module's own section. Claims marked *unverified* are
unproven data, not fact — do not promote them without a live check.

---

## 1. Purpose

`local/` answers three questions and returns the answers as frozen data:

1. **What is running on this machine?** — `discover.py`
2. **What can that model actually do?** — `capabilities.py`
3. **What will it silently get wrong?** — `quirktable.py`

`target.py` folds those into one `LocalTarget`. `manage.py` returns *remedy data* (command
lines, PATH facts) without executing anything. `embed.py` returns an `EmbeddingTarget`.

Behaviour — request mutation, retries, schema rewriting, streaming repair — lives in
`llm/adapters/` and is out of scope. See §12.

---

## 2. The two hard constraints

### 2.1 Dependency sink

Every file in `local/` may import **only** (a) the Python standard library and (b) sibling
modules inside `local/` via **single-dot** relative imports.

Forbidden without exception: any `praisonaiagents` import (absolute or `..`-relative),
`litellm`, `openai`, `pydantic`, `httpx`, `requests`, `aiohttp`, `anyio`, `rich`, `yaml`,
`posthog`, and any other distribution.

### 2.2 Data, never behaviour

Every public return value is a frozen, slotted, hashable dataclass, or a `frozenset`/`tuple`
of them. `local/` must never mutate a request payload, retry, sleep-and-retry, issue a
chat/completion/embedding **inference** call, start or stop a process, write to disk, or read
a config file. The only writes anywhere are two process-local dicts in `target.py` (§9).

Allowed HTTP: `GET`, plus exactly one `POST` — `POST {base}/api/show {"model": ...}` — which
reads a manifest, performs no inference, and does not load weights (verified).

---

## 3. Decision: HTTP client is stdlib `urllib.request`

**This overrides the ledger's earlier suggestion of `httpx`.** The reasoning:

`httpx==0.28.1` is installed, but only **transitively**: `openai -> httpx`. `pyproject.toml`
never declares it. Building a dependency sink on an undeclared transitive edge means a future
`openai` release that drops `httpx` silently breaks `local/` — exactly the class of silent
failure this package exists to catalogue. Declaring it would either add an 18th extra (making
the sink optional, so the bypass sites still cannot rely on it) or add a hard dependency to
the one package whose selling point is that everything can import it.

`aiohttp` *is* a hard dependency, but it is async-only — forcing an event loop into the
synchronous `Agent.__init__` — and costs ~40 ms to import on a hot path.

The cited weaknesses of `urllib.request` do not bite here. **No pooling:** a full resolve
issues at most 4 loopback requests, then caches for 30 s. **Clumsy timeouts:**
`urlopen(req, timeout=t)` applies `t` to connect and to each socket read, which is all
loopback needs; the total budget is enforced by the caller. **No concurrency:**
`concurrent.futures.ThreadPoolExecutor` is stdlib and handles the port fan-out.

The boundary test hard-forbids `httpx`/`requests`/`aiohttp` so this cannot drift.

---

## 4. Layering and naming

### 4.1 Module layers (acyclic; layer *n* imports only layers < *n*)

| Layer | Module | May import |
|---|---|---|
| 0 | `capabilities.py` | stdlib only (`enum`, `dataclasses`, `typing`, `json`) |
| 1 | `quirktable.py` | stdlib, `.capabilities` |
| 1 | `discover.py` | stdlib (`urllib.request`, `urllib.error`, `json`, `os`, `socket`, `time`, `concurrent.futures`, `dataclasses`, `enum`, `typing`), `.capabilities` |
| 2 | `target.py` | stdlib (`os`, `time`, `threading`, `asyncio`, `functools`, `urllib.parse`, `ipaddress`, `dataclasses`, `typing`), `.capabilities`, `.quirktable`, `.discover` |
| 3 | `manage.py` | stdlib (`shutil`, `dataclasses`, `enum`, `typing`), `.capabilities`, `.discover`, `.target` |
| 3 | `embed.py` | stdlib, `.capabilities`, `.discover`, `.target` |
| 4 | `__init__.py` | the five above |

`capabilities.py` is the **vocabulary module**: it owns `LocalEngine`, `ApiStyle`, `Cap` and
`Evidence` in addition to the capability parsers. This is the only placement that yields a
cycle-free graph across the fixed 7-file layout.

### 4.2 Naming collision audit

The name `runtime` is **taken**: `praisonaiagents/runtime/` is the agent-execution harness,
`pyproject.toml` declares a `praisonai.runtimes` entry-point group, and examples use
"runtime" for tool sandboxes.

| Name | Already exists at | Ruling |
|---|---|---|
| `runtime`, `Runtime`, `*Runtime*` | `praisonaiagents/runtime/` | **Banned.** Use `engine`. |
| `RuntimeCapability`, `RuntimeCapabilityMatrix` | `runtime/capabilities.py:19,50` | Banned. Ours is `Cap`. |
| `resolve_runtime()` | `runtime/resolve.py:232` | Ours is `local.resolve()`, namespace-qualified only. Never re-export a bare `resolve`; if ever promoted, the name is `resolve_local`. |
| `RuntimeResolver`, `RuntimeResolutionResult` | `runtime/resolve.py:67`, `runtime/resolver.py:37` | Banned. |
| `ProbeResult` | `bots/protocols.py:651` | **Banned.** Ours are `ProbeSpec`, `Discovery`, `HttpReply`. |
| `CapabilityValidator`, `CapabilityDescriptor` | `skills/capability_validator.py:74`, `gateway/protocols.py:5460` | Banned. |
| `capabilities.py`, `embed.py` (basenames) | `runtime/`, `embedding/` | **Allowed** — different dotted paths, relative imports only. Do not "fix" by renaming. Note `embedding/embed.py` exposes `embedding()`; ours exposes `embedding_target()`. Never name anything in `local/` `embedding()`. |
| `engine`, `Engine`, `LocalEngine`, `Quirk`, `ApiStyle`, `LocalTarget`, `Cap` | no hits | **Free.** Adopted. |

`local/` is **not** added to `_LAZY_IMPORTS` in `praisonaiagents/__init__.py`, and **no** new
extra is added to `pyproject.toml`.

### 4.3 Sync vs async

**Both, sync-primary.** `discover()`, `resolve()`, `capabilities()`, `models()`,
`embedding_target()` are the primitives. Each has an `a`-prefixed twin implemented as exactly:

```python
async def aresolve(*args: Any, **kwargs: Any) -> LocalTarget:
    """Async twin of resolve(); runs the sync probe in the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(resolve, *args, **kwargs))
```

`Agent.__init__` is synchronous and may be called from inside a running event loop; an
async-native core would force `asyncio.run()` (which raises there) or a hand-rolled asyncio
HTTP parser. The executor costs one thread for <= 1.5 s, and only on a cache miss. Both twins
share one cache and one lock.

### 4.4 `LocalTarget` carries `litellm_model`

**Yes**, as `Optional[str]`, computed by the pure function `litellm_model_for(engine, model_id)`.

Without it, each bypass site re-derives a prefix, and they have already diverged:
`llm/llm.py:_detect_provider()` knows only `ollama/`; `llm/model_providers.py` matches only
`model.startswith("ollama/")`; `llm/openai_client.py:_supports_responses_api` knows `ollama/`
**and** `ollama_chat/`; `agent/agent.py:_PROVIDER_DEFAULT_MODELS` hardcodes `ollama/llama3.2`.
A pure `(engine, model_id) -> str` mapping is data, so §2.2 holds.

| `engine` | `litellm_model` | Caller must also pass |
|---|---|---|
| `OLLAMA` | `f"ollama/{model_id}"` | `api_base=target.base_url` |
| `LM_STUDIO` | `f"lm_studio/{model_id}"` | `api_base=target.openai_base_url` |
| `VLLM` | `f"hosted_vllm/{model_id}"` | `api_base=target.openai_base_url` |
| all others | `f"openai/{model_id}"` | `api_base=target.openai_base_url`, `api_key=target.api_key` |
| any engine with `model_id is None` | `None` | — |

**`OLLAMA` maps to `ollama/`, never `ollama_chat/`** — even though `ollama_chat/` is the
better litellm route — because `_detect_provider()` returns `"openai"` for an `ollama_chat/`
model, silently losing `OllamaAdapter` and its streaming guard. Revisit only after work order
`02` teaches that call site the extra prefixes.

---

## 5. Data model

### 5.1 `capabilities.py` — vocabulary

```python
class LocalEngine(str, Enum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"                    # llama.cpp llama-server
    MLX_LM = "mlx_lm"                          # mlx_lm.server (Apple silicon)
    LM_STUDIO = "lm_studio"
    VLLM = "vllm"                              # Linux only
    TRANSFORMERS_SERVE = "transformers_serve"
    LLAMAFILE = "llamafile"
    LOCALAI = "localai"
    RAMALAMA = "ramalama"
    UNKNOWN = "unknown"                        # OpenAI-shaped server; identity not established

class ApiStyle(str, Enum):
    OPENAI_CHAT = "openai_chat"                # POST {base}/v1/chat/completions
    OPENAI_COMPLETIONS = "openai_completions"  # POST {base}/v1/completions only
    OLLAMA_NATIVE = "ollama_native"            # POST {base}/api/chat

class Cap(str, Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    TOOLS = "tools"                            # model trained for tool calls AND server exposes them
    VISION = "vision"
    AUDIO_IN = "audio_in"
    THINKING = "thinking"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"
    STREAMING = "streaming"
    STREAMING_WITH_TOOLS = "streaming_with_tools"
    PARALLEL_TOOL_CALLS = "parallel_tool_calls"
    EMBEDDINGS_ENDPOINT = "embeddings_endpoint"    # engine-level, always Evidence.TABLE

class Evidence(str, Enum):
    SERVER = "server"    # read out of a live response field
    TABLE = "table"      # this package's static per-engine default
    ENV = "env"          # asserted by an environment variable
    SPEC = "spec"        # asserted by the caller's `spec` argument
    UNKNOWN = "unknown"
```

### 5.2 `quirktable.py` — the silent-failure catalogue

```python
class Severity(str, Enum):
    SILENT = "silent"  # wrong result, no error surface — the dangerous class
    HARD = "hard"      # the request fails loudly (4xx/5xx)
    COST = "cost"      # correct result, unexpected latency or resource cost

class Quirk(str, Enum):
    # --- Ollama, verified 0.33.2 ---
    FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE = "format_and_tools_mutually_destructive"
    TOOL_SCHEMA_KEYWORDS_STRIPPED = "tool_schema_keywords_stripped"
    TOOL_PARAM_TYPE_MUST_BE_BARE_STRING = "tool_param_type_must_be_bare_string"
    UNKNOWN_OPTIONS_ACCEPTED_AND_IGNORED = "unknown_options_accepted_and_ignored"
    THINK_FIELD_IGNORED_ON_OPENAI_ROUTE = "think_field_ignored_on_openai_route"
    THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN = "thinking_with_tools_yields_empty_turn"
    NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON = "native_route_never_sets_tool_finish_reason"
    TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL = "tool_calls_arrive_whole_not_incremental"
    STREAM_ERROR_ENDS_WITHOUT_DONE = "stream_error_ends_without_done"
    SAMPLING_DEFAULTS_FORCED_TO_ONE = "sampling_defaults_forced_to_one"
    CONTEXT_OPTION_CHANGE_RELOADS_MODEL = "context_option_change_reloads_model"
    KEEP_ALIVE_IS_GLOBAL_LAST_WRITER_WINS = "keep_alive_is_global_last_writer_wins"
    BODYLESS_403_ON_NON_LOCAL_HOST_HEADER = "bodyless_403_on_non_local_host_header"
    # --- other engines ---
    TOOLS_REQUIRE_SERVER_FLAGS = "tools_require_server_flags"
    NO_JSON_SCHEMA_SUPPORT = "no_json_schema_support"
    NO_EMBEDDINGS_ENDPOINT = "no_embeddings_endpoint"
    SINGLE_MODEL_PER_PROCESS = "single_model_per_process"
    MODEL_ID_IS_A_FILE_PATH = "model_id_is_a_file_path"
    CAPS_ASSUMED_ENGINE_UNIDENTIFIED = "caps_assumed_engine_unidentified"

@dataclass(frozen=True, slots=True)
class QuirkNote:
    quirk: Quirk
    engines: tuple[LocalEngine, ...]
    api_styles: tuple[ApiStyle, ...]   # empty == all styles
    severity: Severity
    symptom: str          # one line, what the user observes
    workaround: str       # one line, what a caller in llm/adapters/ should do
    verified_on: str      # "ollama 0.33.2 @ 2026-09-03" or "unverified: vendor docs"
    requires_caps: frozenset[Cap] = frozenset()
```

Meaning of each Ollama quirk, one line each:

| Quirk | Symptom | Severity |
|---|---|---|
| `FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE` | JSON format + tools suppresses the tool call; the model fabricates an answer | SILENT |
| `TOOL_SCHEMA_KEYWORDS_STRIPPED` | `minLength`, `format`, `default`, `additionalProperties`, `$ref`, `oneOf` dropped before the model sees them | SILENT |
| `TOOL_PARAM_TYPE_MUST_BE_BARE_STRING` | `"type": ["object","null"]` 400s the whole request | HARD |
| `UNKNOWN_OPTIONS_ACCEPTED_AND_IGNORED` | Unrecognised `options` keys return 200 and change nothing | SILENT |
| `THINK_FIELD_IGNORED_ON_OPENAI_ROUTE` | `think` dropped on `/v1/*`; use `reasoning_effort` | SILENT |
| `THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN` | Empty content, zero tool calls, `finish_reason="stop"` | SILENT |
| `NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON` | `/api/chat` reports "stop" even with `tool_calls` present | SILENT |
| `TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL` | Streamed tool calls come in one chunk, not deltas | SILENT |
| `STREAM_ERROR_ENDS_WITHOUT_DONE` | Mid-stream failure yields an empty delta and no `[DONE]` | SILENT |
| `SAMPLING_DEFAULTS_FORCED_TO_ONE` | Omitted `temperature`/`top_p` become 1.0, not the model's defaults | SILENT |
| `CONTEXT_OPTION_CHANGE_RELOADS_MODEL` | Changing `num_ctx`/`num_batch`/`num_gpu` forces a full reload | COST |
| `KEEP_ALIVE_IS_GLOBAL_LAST_WRITER_WINS` | `keep_alive` is per-model and process-wide, not per-request | SILENT |
| `BODYLESS_403_ON_NON_LOCAL_HOST_HEADER` | Non-local `Host` header gets HTTP 403 with a zero-byte body | HARD |
| `TOOLS_REQUIRE_SERVER_FLAGS` | Tool calls come back as assistant text (vLLM needs BOTH `--enable-auto-tool-choice` AND `--tool-call-parser`; llama-server needs `--jinja`) | SILENT |
| `SINGLE_MODEL_PER_PROCESS` | The request's `model` field is ignored — asking for B gets A's answer | SILENT |
| `MODEL_ID_IS_A_FILE_PATH` | The reported model id is a filesystem path | SILENT |
| `CAPS_ASSUMED_ENGINE_UNIDENTIFIED` | Engine is `UNKNOWN`; every `Cap` is `Evidence.TABLE` guesswork | SILENT |

Route scoping (normative): `NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON` is
`api_styles=(OLLAMA_NATIVE,)`; `THINK_FIELD_IGNORED_ON_OPENAI_ROUTE` and
`SAMPLING_DEFAULTS_FORCED_TO_ONE` are `api_styles=(OPENAI_CHAT, OPENAI_COMPLETIONS)`;
`THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN` is `requires_caps={Cap.THINKING, Cap.TOOLS}`;
`TOOLS_REQUIRE_SERVER_FLAGS` is `engines=(VLLM, LLAMA_CPP, LLAMAFILE)`;
`CAPS_ASSUMED_ENGINE_UNIDENTIFIED` is `engines=(UNKNOWN,)`. Everything else in the Ollama
block is `engines=(OLLAMA,)`, all styles.

`quirktable.py` performs no network, no I/O and reads no environment variable.

### 5.3 `discover.py` — probing types

```python
@dataclass(frozen=True, slots=True)
class HttpReply:
    status: int            # 0 == transport failure (refused/timeout/DNS)
    body: bytes            # b"" when bodyless
    error: str | None      # "refused" | "timeout" | "reset" | "http" | None

class RuleKind(str, Enum):
    BODY_PREFIX = "body_prefix"          # 200 and body.lstrip() startswith value
    JSON_KEY = "json_key"                # 200, body is a JSON object, value is a top-level key
    JSON_KEY_PREFIX = "json_key_prefix"  # value "key=prefix"; str(obj[key]).startswith(prefix)
    STATUS_OK = "status_ok"              # 200 <= status < 300, body ignored
    ABSENT = "absent"                    # status is 404/405, or body does not parse as JSON

@dataclass(frozen=True, slots=True)
class Rule:
    method: str            # "GET" or "POST"
    path: str              # appended to base_url verbatim, e.g. "/api/version"
    kind: RuleKind
    value: str = ""

@dataclass(frozen=True, slots=True)
class ProbeSpec:
    engine: LocalEngine
    default_ports: tuple[int, ...]
    identity: tuple[Rule, ...]     # ALL must hold; evaluated in order, short-circuit
    version_path: str | None
    version_key: str | None
    models_path: str | None
    models_key: str | None         # "models[].model" or "data[].id"
    model_caps: Rule | None
    api_style: ApiStyle
    verified: bool
    note: str

@dataclass(frozen=True, slots=True)
class Discovery:
    engine: LocalEngine
    base_url: str                  # "http://127.0.0.1:11434" — no trailing slash, no /v1
    api_style: ApiStyle
    engine_version: str | None
    models: tuple[str, ...]        # () when unknown
    raw_identity: str              # first 200 chars of the identity reply, for diagnostics
    latency_ms: int
    blocked: str | None            # None | "host_header_rejected" | "auth_required"
    evidence: Evidence

class Transport(Protocol):
    def __call__(self, method: str, url: str, body: bytes | None, timeout: float) -> HttpReply: ...
```

The default `Transport` is built inside `discover.py` and is the only thing in the package
that touches a socket.

### 5.4 `target.py` — the product

```python
@dataclass(frozen=True, slots=True)
class LocalTarget:
    engine: LocalEngine
    base_url: str                                # no trailing slash, no /v1
    openai_base_url: str                         # base_url + "/v1"
    api_style: ApiStyle
    model_id: str | None
    caps: frozenset[Cap]
    quirks: frozenset[Quirk]
    litellm_model: str | None
    api_key: str                                 # placeholder "local"; never "" (openai rejects "")
    engine_version: str | None
    evidence: tuple[tuple[str, Evidence], ...]   # sorted by field name; per-field provenance
    extra: tuple[tuple[str, str], ...]           # sorted by key; engine-specific facts
    probed_at: float

    def supports(self, cap: Cap) -> bool: ...
    def has_quirk(self, quirk: Quirk) -> bool: ...
    def evidence_for(self, field: str) -> Evidence: ...   # Evidence.UNKNOWN if absent
    def get_extra(self, key: str, default: str | None = None) -> str | None: ...
    def as_dict(self) -> dict[str, object]: ...           # JSON-safe, for logs and doctors
```

`evidence`/`extra` are **tuples of pairs, not dicts**, so `LocalTarget` stays frozen *and*
hashable — a `dict` field would make the generated `__hash__` raise `TypeError` at runtime.

### 5.5 Exceptions (defined in `target.py`)

```python
class LocalError(Exception): ...
class NoLocalEngineError(LocalError): ...
class EngineUnreachableError(LocalError):
    base_url: str
    reason: str          # "refused" | "timeout" | "reset" | "http_<status>"
    source: str          # "spec" | "PRAISONAI_LOCAL_BASE_URL" | "OLLAMA_HOST" | ...
class HostHeaderRejectedError(EngineUnreachableError): ...
class ModelNotAvailableError(LocalError):
    model_id: str
    available: tuple[str, ...]
class InvalidLocalSpecError(LocalError, ValueError): ...
```

`local/` deliberately does **not** subclass `praisonaiagents.errors.PraisonAIError` — that
would import upward and break §2.1. Wrapping is the integration layer's job.

---

## 6. `capabilities.py`

```python
"""Local-engine vocabulary and capability resolution (layer 0: stdlib only)."""

DEFAULT_CAPS: Mapping[LocalEngine, frozenset[Cap]]   # exhaustive over LocalEngine

def default_caps(engine: LocalEngine) -> frozenset[Cap]:
    """Return the static per-engine capability floor (no network, Evidence.TABLE)."""
    # Raises nothing; an unrecognised value returns DEFAULT_CAPS[LocalEngine.UNKNOWN].

def parse_ollama_capabilities(payload: Mapping[str, Any]) -> frozenset[Cap]:
    """Map an Ollama /api/show or /api/tags entry's `capabilities` list onto Cap.

    "completion"->COMPLETION+CHAT, "tools"->TOOLS, "vision"->VISION,
    "thinking"->THINKING, "embedding"->EMBEDDINGS_ENDPOINT, "insert"->ignored.
    Unknown strings are ignored, never raised on.
    """

def parse_llama_cpp_props(payload: Mapping[str, Any]) -> frozenset[Cap]: ...
def parse_lm_studio_models(payload: Mapping[str, Any], model_id: str | None) -> frozenset[Cap]: ...
def parse_openai_models(payload: Mapping[str, Any]) -> tuple[str, ...]: ...

def capabilities(
    discovery: Discovery,
    model_id: str | None = None,
    *,
    timeout: float = 0.4,
    transport: Transport | None = None,
) -> tuple[frozenset[Cap], Evidence]:
    """Resolve capabilities for one model on one discovered engine.

    Issues at most one request (the engine's ProbeSpec.model_caps). Returns
    (caps, Evidence.SERVER) when it answered and parsed, else
    (default_caps(engine), Evidence.TABLE). Server caps are unioned with the
    engine's EMBEDDINGS_ENDPOINT / STREAMING floor from DEFAULT_CAPS.
    """
    # Raises nothing. Every transport and parse failure degrades to TABLE.

async def acapabilities(...) -> tuple[frozenset[Cap], Evidence]: ...
```

`DEFAULT_CAPS` (normative floor):

| engine | caps |
|---|---|
| `OLLAMA` | `CHAT, COMPLETION, STREAMING, JSON_OBJECT, JSON_SCHEMA, EMBEDDINGS_ENDPOINT` |
| `LLAMA_CPP` | `CHAT, COMPLETION, STREAMING, JSON_SCHEMA, JSON_OBJECT, EMBEDDINGS_ENDPOINT` |
| `MLX_LM` | `CHAT, COMPLETION, STREAMING` |
| `LM_STUDIO` | `CHAT, COMPLETION, STREAMING, JSON_SCHEMA, JSON_OBJECT, EMBEDDINGS_ENDPOINT` |
| `VLLM` | `CHAT, COMPLETION, STREAMING, JSON_SCHEMA, JSON_OBJECT, EMBEDDINGS_ENDPOINT, PARALLEL_TOOL_CALLS` |
| `TRANSFORMERS_SERVE` | `CHAT, STREAMING` |
| `LLAMAFILE`, `LOCALAI`, `RAMALAMA` | `CHAT, COMPLETION, STREAMING` |
| `UNKNOWN` | `CHAT, STREAMING` |

`Cap.TOOLS` and `Cap.VISION` are **never** in `DEFAULT_CAPS` — claiming them without server
evidence is exactly the silent failure this package prevents. `Cap.STREAMING_WITH_TOOLS` is
granted only when the server reports `TOOLS` **and** the engine's quirk set lacks
`TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL`.

---

## 7. `discover.py` and the probe table

```python
PROBES: tuple[ProbeSpec, ...]
LOOPBACK_HOST: str = "127.0.0.1"
DEFAULT_PROBE_TIMEOUT: float = 0.4     # seconds, per request
DEFAULT_TOTAL_BUDGET: float = 1.5      # seconds, whole scan

def probe_table() -> tuple[ProbeSpec, ...]: ...

def probe_endpoint(
    base_url: str, *, expect: LocalEngine | None = None,
    timeout: float = DEFAULT_PROBE_TIMEOUT, transport: Transport | None = None,
) -> Discovery | None:
    """Identify the server at base_url, or None if nothing identifiable answered.

    A 200 matching no discriminator yields Discovery(engine=UNKNOWN). A bodyless
    403 yields Discovery(..., blocked="host_header_rejected").
    """
    # Raises InvalidLocalSpecError for a URL with no host or an unsupported scheme.
    # Never raises for any network or parse condition.

def discover(
    *, ports: Sequence[int] | None = None, include: Sequence[LocalEngine] | None = None,
    host: str = LOOPBACK_HOST, timeout: float = DEFAULT_PROBE_TIMEOUT,
    budget: float = DEFAULT_TOTAL_BUDGET, transport: Transport | None = None,
) -> tuple[Discovery, ...]:
    """Scan the probe table's default ports; return every server found.

    Ports probed concurrently (ThreadPoolExecutor, max_workers=8). Ordered by
    PROBES order, then port. Includes `blocked` discoveries.
    """
    # Raises nothing.

async def adiscover(...) -> tuple[Discovery, ...]: ...
def models(discovery, *, timeout=0.4, transport=None) -> tuple[str, ...]: ...
async def amodels(...) -> tuple[str, ...]: ...
```

### 7.1 The probe table (actual literal)

Port collisions are real: **8080** is claimed by `llama-server`, `mlx_lm`, `llamafile`,
LocalAI and RamaLama; **8000** by vLLM and `transformers serve`. Identity is therefore
**never** inferred from a port — a `ProbeSpec` matches only when every `Rule` in `identity`
holds, and `RuleKind.ABSENT` rules exist specifically to separate co-tenants of one port.

```python
PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec(
        engine=LocalEngine.OLLAMA,
        default_ports=(11434,),
        identity=(Rule("GET", "/", RuleKind.BODY_PREFIX, "Ollama is running"),),
        version_path="/api/version", version_key="version",
        models_path="/api/tags", models_key="models[].model",
        model_caps=Rule("POST", "/api/show", RuleKind.JSON_KEY, "capabilities"),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=True,
        note="verified 0.33.2 @ 2026-09-03: GET / -> 'Ollama is running'; "
             "/api/version -> {'version':'0.33.2'}; /api/tags entries carry both "
             "`capabilities` and `modified_at`; POST /api/show carries capabilities, "
             "details and model_info.",
    ),
    ProbeSpec(
        engine=LocalEngine.LLAMA_CPP,
        default_ports=(8080,),
        identity=(Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/props", RuleKind.JSON_KEY, "build_info")),
        version_path="/props", version_key="build_info",
        models_path="/v1/models", models_key="data[].id",
        model_caps=Rule("GET", "/props", RuleKind.JSON_KEY, "modalities"),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note="binary present (build 7620), --port default 8080 confirmed from --help; "
             "GET /props reply shape NOT re-verified live. Tool calls need a "
             "tools-capable template (--jinja).",
    ),
    ProbeSpec(
        engine=LocalEngine.MLX_LM,
        default_ports=(8080,),
        identity=(Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/props", RuleKind.ABSENT),
                  Rule("GET", "/v1/models", RuleKind.JSON_KEY, "data")),
        version_path=None, version_key=None,
        models_path="/v1/models", models_key="data[].id",
        model_caps=None,
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note="mlx_lm.server present on PATH; default port 8080; identity is "
             "'/health answers AND /props does not' to separate it from llama.cpp on "
             "the same port. No JSON-schema support, no embeddings endpoint.",
    ),
    ProbeSpec(
        engine=LocalEngine.LM_STUDIO,
        default_ports=(1234,),
        identity=(Rule("GET", "/api/v0/models", RuleKind.JSON_KEY, "data"),),
        version_path=None, version_key=None,
        models_path="/api/v0/models", models_key="data[].id",
        model_caps=Rule("GET", "/api/v0/models", RuleKind.JSON_KEY, "data"),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note="LM Studio not installed on this machine. /api/v0/models is richer than "
             "/v1/models and is the discriminator. Use HTTP, not the Python SDK "
             "(last release Aug 2025, WebSocket-based, stale).",
    ),
    ProbeSpec(
        engine=LocalEngine.VLLM,
        default_ports=(8000,),
        identity=(Rule("GET", "/version", RuleKind.JSON_KEY, "version"),),
        version_path="/version", version_key="version",
        models_path="/v1/models", models_key="data[].id",
        model_caps=Rule("GET", "/server_info", RuleKind.JSON_KEY, "vllm_config"),
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note="Linux only; not installable on this machine. Tools require BOTH "
             "--enable-auto-tool-choice AND --tool-call-parser, otherwise tool calls "
             "come back as plain text (Quirk.TOOLS_REQUIRE_SERVER_FLAGS).",
    ),
    ProbeSpec(
        engine=LocalEngine.TRANSFORMERS_SERVE,
        default_ports=(8000,),
        identity=(Rule("GET", "/version", RuleKind.ABSENT),
                  Rule("GET", "/health", RuleKind.STATUS_OK),
                  Rule("GET", "/v1/models", RuleKind.JSON_KEY, "data")),
        version_path=None, version_key=None,
        models_path="/v1/models", models_key="data[].id",
        model_caps=None,
        api_style=ApiStyle.OPENAI_CHAT,
        verified=False,
        note="`transformers serve`, default 8000; /health is undocumented. Identity is "
             "'/version absent AND /health ok' to separate it from vLLM on 8000.",
    ),
)
```

`LLAMAFILE`, `LOCALAI` and `RAMALAMA` are enum members with `DEFAULT_CAPS` entries but **no
`ProbeSpec`**: they are reachable only via `PRAISONAI_LOCAL_ENGINE`. Adding a row requires a
discriminator verified on a live server. A `ProbeSpec` with `verified=False` is still probed —
it is the *note* that is unproven, not the port.

---

## 8. `target.py` — `resolve()` and precedence

```python
DEFAULT_API_KEY: str = "local"
ENV_BASE_URL: str = "PRAISONAI_LOCAL_BASE_URL"
ENV_ENGINE:   str = "PRAISONAI_LOCAL_ENGINE"
ENV_MODEL:    str = "PRAISONAI_LOCAL_MODEL"
ENV_TTL:      str = "PRAISONAI_LOCAL_TTL"
ENV_NEG_TTL:  str = "PRAISONAI_LOCAL_NEG_TTL"
ENV_TIMEOUT:  str = "PRAISONAI_LOCAL_TIMEOUT"

def resolve(spec=None, *, timeout=None, refresh=False, transport=None) -> LocalTarget: ...
async def aresolve(...) -> LocalTarget: ...
def resolve_or_none(spec=None, **kwargs) -> LocalTarget | None: ...
async def aresolve_or_none(...) -> LocalTarget | None: ...
def build_target(discovery, model_id, *, caps=None, caps_evidence=Evidence.TABLE,
                 model_evidence=Evidence.SERVER) -> LocalTarget: ...   # pure
def litellm_model_for(engine, model_id) -> str | None: ...             # pure
def parse_spec(spec) -> tuple[LocalEngine | None, str | None, str | None]: ...
def parse_ollama_host(value: str) -> str | None: ...
def select_model(discovery, *, transport=None, timeout=0.4) -> str | None: ...
def clear_cache() -> None: ...
def cache_info() -> dict[str, int]: ...
```

`parse_ollama_host` applies Ollama's own rules: empty/whitespace -> `None`; contains `://` ->
parsed as a URL where an absent port means **80 for http and 443 for https, not 11434**; all
digits (`"11500"`) or a leading colon (`":11500"`) -> `http://127.0.0.1:11500`; otherwise
`host[:port]` with default port 11434 and scheme http. IPv6 must be bracketed; an unbracketed
IPv6 literal returns `None`.

### 8.1 Resolution precedence

Sources are consulted in this order. **Authoritative** means its failure raises;
**inferential** means its failure falls through.

1. **`spec` argument — authoritative.**
   - `None` / `""` / `"local"` / `"auto"` -> contributes nothing; go to 2.
   - `"<engine>/<model>"` -> pins `engine` and `model_id` (`Evidence.SPEC`); the base URL
     still comes from 2-5, restricted via `probe_endpoint(expect=engine)`.
   - a URL -> pins `base_url`; an optional `#model` fragment pins `model_id`. Probed for
     identity; answering but matching no discriminator gives `engine=UNKNOWN`.
   - anything else -> `InvalidLocalSpecError(f"Cannot parse local spec {spec!r}. Expected None, 'local', '<engine>/<model>', a base URL, or '<url>#<model>'.")`
   - A pinned `base_url` that does not answer -> `EngineUnreachableError(source="spec")`.
     **No fallback** — silently talking to a different server than the caller named is the
     failure mode this package exists to prevent.
2. **`PRAISONAI_LOCAL_BASE_URL` — authoritative.** `PRAISONAI_LOCAL_ENGINE`, if set to a valid
   `LocalEngine` value, skips identity probing and pins the engine (`Evidence.ENV`); an
   invalid value raises `InvalidLocalSpecError`.
3. **`OLLAMA_HOST` — authoritative.** Via `parse_ollama_host()`, with `expect=OLLAMA`. This is
   where the bare-host / `http://` asymmetry bites, which is why the error must print the
   resolved URL.
4. **`OPENAI_BASE_URL`, then `OPENAI_API_BASE` — inferential.** Used **only** if the host is
   loopback (`127.0.0.0/8`, `::1`, `localhost`) or RFC1918/link-local. A public host is
   ignored — it is normally a cloud proxy. Falls through to 5, recording the skip reason.
5. **Probe-table scan — inferential.** `discover(host="127.0.0.1")` in table order, ports
   concurrent, within `budget`. The first non-`blocked` `Discovery` in table order wins, so
   Ollama on 11434 beats an unidentified server on 8000.
6. **Nothing found.** If step 5 produced only `blocked` discoveries, raise
   `HostHeaderRejectedError`. Otherwise `NoLocalEngineError`.

### 8.2 Error message templates (exact)

```
No local model runtime found. Probed 127.0.0.1 ports 11434 (ollama), 8080 (llama_cpp, mlx_lm), 1234 (lm_studio), 8000 (vllm, transformers_serve) in 1.5s; nothing answered. Start one (e.g. `ollama serve`, then `ollama pull qwen3:0.6b`) or set PRAISONAI_LOCAL_BASE_URL to its address.
```
When step 4 was skipped for being non-local, append exactly:
` Ignored OPENAI_BASE_URL='https://api.openai.com/v1': not a local address.`

```
Local runtime at http://127.0.0.1:80 did not answer (refused). It was named explicitly by OLLAMA_HOST='http://127.0.0.1', so no other port was probed. Note that OLLAMA_HOST with an explicit http:// scheme and no port means port 80, not 11434.
```
The trailing sentence appears only when `source == "OLLAMA_HOST"` and the parsed port is 80 or 443.

```
Local runtime at http://192.168.1.10:11434 returned HTTP 403 with an empty body. Ollama rejects any request whose Host header is not localhost or an IP address; set OLLAMA_HOST on the server to allow this origin.
```

```
Model 'llama3.2' is not served by ollama at http://127.0.0.1:11434. Available: qwen3:0.6b, mervinpraison/praisonai-qwen3.5-9b-tamil-en2ta:latest. Pull it with `ollama pull llama3.2`.
```

### 8.3 `select_model()` — deterministic choice

Applied only when no source pinned a model:

1. `PRAISONAI_LOCAL_MODEL` if set — validated against the model list; a miss raises `ModelNotAvailableError`.
2. If the engine has `Quirk.SINGLE_MODEL_PER_PROCESS` -> the single id reported, or `None`.
3. If the list has exactly one entry -> that entry.
4. Otherwise prefer entries whose reported capabilities include `tools` (Ollama's `/api/tags`
   carries `capabilities` per entry — verified); tie-break newest `modified_at`; final
   tie-break lexicographic ascending. **Never** guess a model not in the list.
5. Empty list -> `None` (and `litellm_model` is `None`).

### 8.4 Timeouts

`timeout=None` -> `float(os.environ.get(ENV_TIMEOUT, "1.5"))`, clamped to `[0.05, 30.0]`; a
non-numeric value falls back to 1.5 without raising. Per-request timeout is
`min(0.4, total/3)`. `resolve()` must return or raise within `total + 0.2` s.

---

## 9. Caching

| Question | Answer |
|---|---|
| **What is cached** | Two dicts in `target.py`: `_TARGETS: dict[str, tuple[float, int, LocalTarget]]` (deadline, pid, target) and `_NEGATIVES: dict[str, tuple[float, int, str, str]]` (deadline, pid, exception class name, message). Nothing else. |
| **Cache key** | `"\x00".join((spec or "*", PRAISONAI_LOCAL_BASE_URL, PRAISONAI_LOCAL_ENGINE, PRAISONAI_LOCAL_MODEL, OLLAMA_HOST, OPENAI_BASE_URL, OPENAI_API_BASE, f"{timeout:.3f}"))`. Every input that can change the answer is in the key, so an env change is a natural miss rather than a stale hit. |
| **TTL** | Positive 30.0 s (`PRAISONAI_LOCAL_TTL`); negative 5.0 s (`PRAISONAI_LOCAL_NEG_TTL`). `0` disables; negative or non-numeric falls back to the default without raising. Negatives are cached so "nothing running" does not cost 1.5 s on every `Agent()` in a loop. |
| **Invalidation** | (a) deadline passed; (b) `refresh=True`; (c) `clear_cache()`; (d) key change; (e) `os.getpid()` differs from the stored pid — a forked child must re-probe rather than inherit the parent's view. |
| **Where** | **Process-local only. Never on disk.** A disk cache goes stale across `ollama pull` / `ollama serve --port`, needs locking and per-user `/tmp` permissions, and is persistent mutable state — i.e. behaviour, which §2.2 forbids. |
| **Thread safety** | One module-level `_CACHE_LOCK = threading.Lock()`, held **only** around dict reads and writes, **never** across I/O. Two threads missing at once both probe; the second write wins; both callers get an equally valid target. `LocalTarget` is frozen, so a shared instance cannot be mutated. `aresolve` runs `resolve` in an executor and shares the same dicts and lock — no second cache. |
| **Re-raise** | A negative hit raises a **fresh** exception built from the stored class name and message — never a stored exception object, which would carry a stale traceback and references to dead frames. |

---

## 10. Failure semantics

`probe_endpoint()` and `discover()` never raise for network conditions.

| Condition | Transport result | `probe_endpoint` | `resolve()` |
|---|---|---|---|
| Connection refused | `HttpReply(0, b"", "refused")` | `None` | authoritative -> `EngineUnreachableError(reason="refused")`; inferential -> skip |
| Timeout | `HttpReply(0, b"", "timeout")` | `None` | as above, `reason="timeout"` |
| Reset / partial read | `HttpReply(0, b"", "reset")` | `None` | as above, `reason="reset"` |
| DNS failure (`socket.gaierror`) | `HttpReply(0, b"", "refused")` | `None` | as above |
| **Bodyless 403** (verified: Ollama, non-local Host header, `size_download=0`) | `HttpReply(403, b"", "http")` | `Discovery(blocked="host_header_rejected")` | skipped as a candidate; if it is the only one -> `HostHeaderRejectedError`; otherwise its reason is appended to `NoLocalEngineError`. **Never** silently reported as "nothing found". |
| 401/403 **with** a body | `HttpReply(401\|403, body, "http")` | `Discovery(blocked="auth_required")` | same handling, different message clause |
| Other 4xx/5xx | `HttpReply(status, body, "http")` | `None` unless an `ABSENT` rule wanted 404/405 | skip / `EngineUnreachableError(reason=f"http_{status}")` |
| Malformed JSON | `HttpReply(200, junk, None)` | `JSON_KEY` rules fail; `ABSENT` rules **succeed**; a matched `BODY_PREFIX`/`STATUS_OK` identity still stands with `models=()` | target built with `caps=default_caps(engine)`, evidence `TABLE`. Never raises. |
| Unknown runtime on a known port (200, no discriminator) | — | `Discovery(engine=UNKNOWN, api_style=OPENAI_CHAT if /v1/models parsed else OPENAI_COMPLETIONS, evidence=TABLE)` | `caps={CHAT, STREAMING}`, `quirks={CAPS_ASSUMED_ENGINE_UNIDENTIFIED}`, `litellm_model=f"openai/{model_id}"`. The quirk is the honest signal that everything here is a guess. |
| Non-UTF-8 body | decoded with `errors="replace"` | per rule | — |
| Reply larger than 1 MiB | truncated at 1 MiB | rules see truncated bytes | — |

The default transport must catch `urllib.error.HTTPError` (a subclass of `URLError` **and** a
response object — read its body, do not let it escape), `urllib.error.URLError`, `OSError`,
`socket.timeout`, `TimeoutError`, `ValueError` (bad URL) and `http.client.HTTPException`. It
must set `Host` implicitly (never override it) and send `Accept: application/json` and
`User-Agent: praisonaiagents-local/1`.

---

## 11. `manage.py` and `embed.py`

### 11.1 `manage.py` — remedy data, executes nothing

```python
class RemedyKind(str, Enum):
    INSTALL = "install"            # engine not on PATH
    START = "start"                # installed but not listening
    PULL_MODEL = "pull_model"      # listening but model absent
    ENABLE_TOOLS = "enable_tools"  # listening but launched without tool flags
    SET_ENV = "set_env"            # reachable but an env var points elsewhere

@dataclass(frozen=True, slots=True)
class Remedy:
    engine: LocalEngine
    kind: RemedyKind
    argv: tuple[str, ...]              # ("ollama", "pull", "qwen3:0.6b"); () for SET_ENV
    env: tuple[tuple[str, str], ...]
    docs_url: str
    note: str

def remedies(engine=None, *, kind=None, model_id=None) -> tuple[Remedy, ...]: ...  # pure
def binary_name(engine) -> str | None: ...
def binary_path(engine) -> str | None: ...            # shutil.which only
def installed_engines() -> tuple[LocalEngine, ...]: ...

@dataclass(frozen=True, slots=True)
class LocalModel:
    model_id: str
    engine: LocalEngine
    size_bytes: int | None
    modified_at: str | None            # ISO-8601 verbatim as the server reports it
    caps: frozenset[Cap]
    family: str | None

def installed_models(discovery, *, timeout=0.4, transport=None) -> tuple[LocalModel, ...]: ...
async def ainstalled_models(...) -> tuple[LocalModel, ...]: ...
```

`manage.py` **never** imports `subprocess`, `os.system`, `os.popen` or `pty`, and never calls
`os.exec*`. It emits `argv` tuples for a caller (a CLI, a doctor, an error message) to run or
print. That is the line between data and behaviour, and it is a test.

### 11.2 `embed.py`

```python
EMBED_DEFAULT_MODELS: Mapping[LocalEngine, str | None]   # OLLAMA -> "nomic-embed-text"

@dataclass(frozen=True, slots=True)
class EmbeddingTarget:
    engine: LocalEngine
    base_url: str
    endpoint: str                  # base_url + "/v1/embeddings", or the native path
    model_id: str | None
    dimensions: int | None         # from server metadata or a static table; None when unknown
    litellm_model: str | None
    api_key: str
    evidence: tuple[tuple[str, Evidence], ...]
    def as_dict(self) -> dict[str, object]: ...

def embedding_target(target, *, model_id=None, timeout=0.4, transport=None) -> EmbeddingTarget:
    """Model choice: model_id > PRAISONAI_LOCAL_EMBED_MODEL > EMBED_DEFAULT_MODELS > None.

    Dimensions come from server metadata only: for Ollama, POST /api/show and read the
    model_info key ending in ".embedding_length" (verified: qwen3.embedding_length == 1024).
    """
    # Raises LocalError when the target carries Quirk.NO_EMBEDDINGS_ENDPOINT or lacks
    # Cap.EMBEDDINGS_ENDPOINT; ModelNotAvailableError when a named model is not served.

async def aembedding_target(...) -> EmbeddingTarget: ...
def default_embed_model(engine) -> str | None: ...
```

**`dimensions` is never obtained by embedding a probe string.** That would be an inference
call — cost, model load, behaviour. `None` is the correct answer when metadata is silent.

### 11.3 `__init__.py`

Re-exports only; no logic, no `os.environ` reads, no lazy machinery (every submodule is
stdlib-only, so eager import is cheap).

```python
__all__ = [
    "LocalEngine", "ApiStyle", "Cap", "Evidence", "Severity", "Quirk",
    "Discovery", "HttpReply", "ProbeSpec", "Rule", "RuleKind", "Transport",
    "discover", "adiscover", "probe_endpoint", "probe_table", "models", "amodels",
    "capabilities", "acapabilities", "default_caps",
    "parse_ollama_capabilities", "parse_llama_cpp_props",
    "parse_lm_studio_models", "parse_openai_models",
    "QuirkNote", "note", "all_notes", "notes_for", "quirks_for", "silent_quirks",
    "LocalTarget", "resolve", "aresolve", "resolve_or_none", "aresolve_or_none",
    "build_target", "litellm_model_for", "parse_spec", "parse_ollama_host",
    "select_model", "clear_cache", "cache_info",
    "Remedy", "RemedyKind", "LocalModel", "remedies", "binary_name", "binary_path",
    "installed_engines", "installed_models", "ainstalled_models",
    "EmbeddingTarget", "embedding_target", "aembedding_target", "default_embed_model",
    "LocalError", "NoLocalEngineError", "EngineUnreachableError",
    "HostHeaderRejectedError", "ModelNotAvailableError", "InvalidLocalSpecError",
]
```

---

## 12. Tests

All under `src/praisonai/tests/unit/llm/local/` — the tree CI actually collects
(`cd src/praisonai && pytest tests/unit/`). Do **not** place them under
`src/praisonai-agents/tests/`, which no workflow runs (see `00-ground-truth.md`); the guards
below would then never execute. Every test carries `pytestmark = pytest.mark.unit`. The markers
`network`, `local_service` and `provider_ollama` are **forbidden** in this directory — a test
needing a live server belongs in `tests/integration/`, out of scope here.

**Files:** `__init__.py`, `conftest.py`, `fixtures/`, `test_import_boundary.py`,
`test_discover.py`, `test_capabilities.py`, `test_quirktable.py`, `test_target.py`,
`test_cache.py`, `test_manage.py`, `test_embed.py`, `test_async_parity.py`.

### 12.1 `conftest.py` provides exactly three things

- **`no_sockets`** (autouse, session-scoped): monkeypatches `socket.socket.__init__` to
  `raise AssertionError("tests/unit/llm/local must not open a socket")`. This is *the* mechanism
  that proves offline safety — a test that forgets to inject a transport fails loudly instead
  of silently hitting a developer's live Ollama.
- **`fake_transport(routes, *, default=HttpReply(0, b"", "refused"))`** — a `Transport`
  callable that also records calls, so tests can assert "exactly one request was made" and
  "no POST was issued".
- **`recorded(name)`** — reads `fixtures/<name>` from disk. No network.

### 12.2 `fixtures/` — byte-for-byte captures from this machine, 2026-09-03

`ollama_root.txt`, `ollama_api_version.json`, `ollama_api_tags.json` (both models, with
`capabilities` and `modified_at`), `ollama_api_show_qwen3_0_6b.json` (`capabilities`,
`details`, `model_info` incl. `qwen3.context_length: 40960`, `qwen3.embedding_length: 1024`),
`ollama_v1_models.json`, plus clearly-labelled hand-written-from-docs
`llama_cpp_props.json`, `lm_studio_api_v0_models.json`, `vllm_version.json`, `malformed.txt`,
`empty_403.bin`.

### 12.3 Test inventory

| File | Test | How it avoids the network |
|---|---|---|
| `test_import_boundary.py` | `test_only_stdlib_imports` | `ast.parse()` each `local/*.py`; every absolute import root must be in `sys.stdlib_module_names`. No import executed. |
| | `test_no_praisonaiagents_import` | AST: no import whose module starts with `praisonaiagents`. |
| | `test_no_parent_relative_imports` | AST: every `ImportFrom` has `level <= 1`. `level >= 2` is the escape hatch that breaks the sink. |
| | `test_forbidden_distributions` | AST: import roots ∩ `{litellm, openai, pydantic, httpx, requests, aiohttp, anyio, rich, yaml, posthog, numpy}` is empty. |
| | `test_loads_standalone_from_file_path` | `importlib.util.spec_from_file_location` loads `local/` **without** executing `praisonaiagents/__init__.py`, proving the sink property. Filesystem only. |
| | `test_no_third_party_in_sys_modules` | After the standalone load, newly-added `sys.modules` contains no forbidden distribution. |
| | `test_import_via_parent_package_also_works` | `import praisonaiagents.local` in a `subprocess -I`; asserts exit 0 and no `litellm`/`openai` in the printed module list. |
| | `test_manage_has_no_subprocess` | AST of `manage.py`: no `subprocess`/`os.system`/`os.popen`/`pty` import, no `os.exec*` call. |
| | `test_sloc_ceiling` | Counts non-blank, non-comment lines per file against §13. Filesystem only. |
| | `test_public_api_is_frozen` | `__all__` equals a literal list held in the test, so an addition is a deliberate edit. |
| `test_discover.py` | `test_ollama_identity_from_recorded_root` | `fake_transport` + recorded fixtures. |
| | `test_ollama_not_matched_by_port_alone` | Transport returns 200 `"hello"` on 11434 → `UNKNOWN`, not `OLLAMA`. |
| | `test_port_8080_collision_llama_cpp_vs_mlx` | `/props` yields `build_info` → `LLAMA_CPP`; `/props` 404 + `/health` 200 → `MLX_LM`. |
| | `test_port_8000_collision_vllm_vs_transformers` | `/version` present → `VLLM`; `/version` 404 + `/health` 200 → `TRANSFORMERS_SERVE`. |
| | `test_connection_refused_yields_no_candidate` | Default transport reply is `refused`; returns `()`, raises nothing. |
| | `test_timeout_yields_no_candidate` | `HttpReply(0, b"", "timeout")`. |
| | `test_bodyless_403_marks_blocked` | `HttpReply(403, b"", "http")`; asserts `blocked == "host_header_rejected"`. |
| | `test_malformed_json_does_not_raise` | `malformed.txt`. |
| | `test_probe_table_rows_are_wellformed` | Pure: unique engines, non-empty `identity`, methods in `{GET, POST}`, paths start with `/`, non-empty `note`. |
| | `test_discover_respects_budget` | Transport counts, never `time.sleep`s; asserts request count ≤ ports × rules. |
| | `test_models_uses_get_only` | Recorded call log has no `POST`. |
| `test_capabilities.py` | `test_parse_ollama_capabilities_covers_recorded_payload` | Recorded show → `{COMPLETION, CHAT, TOOLS, THINKING}`. |
| | `test_unknown_capability_string_is_ignored` | Pure `{"capabilities": ["teleportation"]}`. |
| | `test_default_caps_exhaustive_over_engines` | Pure. |
| | `test_default_caps_never_claim_tools_or_vision` | Pure. |
| | `test_llama_cpp_props_modalities` | Recorded fixture. |
| | `test_capabilities_degrades_to_table_on_failure` | Transport `refused` → `(default_caps(engine), Evidence.TABLE)`. |
| | `test_pure_parsers_take_no_transport` | `inspect.signature` has no `transport` parameter. |
| `test_quirktable.py` | `test_every_quirk_has_a_note` | Pure: `set(Quirk) == set(NOTES)`. |
| | `test_every_note_is_self_consistent` | Pure: key matches `note.quirk`; `engines` non-empty; strings non-empty. |
| | `test_ollama_openai_route_quirks` | Pure: contains `THINK_FIELD_IGNORED_ON_OPENAI_ROUTE` + `THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN`, excludes `NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON`. |
| | `test_ollama_native_route_quirks` | Pure: the inverse. |
| | `test_thinking_quirk_requires_both_caps` | Pure: absent when `TOOLS` not in `caps`. |
| | `test_unknown_engine_gets_caps_assumed_quirk` | Pure. |
| | `test_quirktable_reads_no_environment` | AST: no `os.environ`/`getenv`. |
| `test_target.py` | `test_precedence_spec_url_wins_over_every_env` | All env set via `monkeypatch`; transport keyed to the spec URL only. |
| | `test_precedence_env_base_url_beats_ollama_host` | `monkeypatch` + transport. |
| | `test_ollama_host_bare_host_defaults_11434` | Pure. |
| | `test_ollama_host_with_scheme_defaults_80` | Pure: `"http://127.0.0.1"` → `":80"`. |
| | `test_ollama_host_bare_port_forms` | Pure: `"11500"` and `":11500"`. |
| | `test_openai_base_url_ignored_when_not_local` | Asserts skip + appended message clause. |
| | `test_openai_base_url_used_when_loopback` | Transport-backed. |
| | `test_explicit_source_unreachable_raises_and_does_not_fall_through` | Transport refuses the pinned URL but would answer on 11434; asserts the raise **and** that 11434 was never requested. |
| | `test_nothing_found_message_is_exact` | Empty transport; asserts the full string equals the §8.2 literal. |
| | `test_blocked_only_raises_host_header_error` | 403-bodyless transport. |
| | `test_model_selection_prefers_tools_then_recency` | Recorded tags → `qwen3:0.6b`. |
| | `test_model_not_available_lists_alternatives` | `PRAISONAI_LOCAL_MODEL=llama3.2` + recorded tags. |
| | `test_litellm_model_for_every_engine` | Pure, parametrised over all members. |
| | `test_ollama_never_maps_to_ollama_chat` | Pure; guards the §4.4 decision. |
| | `test_target_is_frozen_and_hashable` | Pure: `hash(t)` works; assignment raises `FrozenInstanceError`. |
| | `test_as_dict_is_json_serialisable` | Pure: `json.dumps(t.as_dict())`. |
| `test_cache.py` | `test_hit_does_not_reprobe` | Counting transport; second call adds zero. |
| | `test_ttl_expiry_reprobes` | `monkeypatch target.time.time`; never sleeps. |
| | `test_refresh_bypasses_cache` | Counting transport. |
| | `test_env_change_changes_key` | `monkeypatch.setenv` between calls. |
| | `test_negative_result_is_cached_and_reraised_fresh` | Asserts two distinct exception objects, identical messages, one probe round. |
| | `test_pid_change_invalidates` | `monkeypatch target.os.getpid`. |
| | `test_concurrent_resolve_is_consistent` | 16 threads, in-memory transport; all results equal, no exception. |
| | `test_clear_cache_empties_both_dicts` | `cache_info()`. |
| `test_manage.py` | `test_remedies_exist_for_every_engine` | Pure. |
| | `test_remedy_argv_is_a_tuple_of_str` | Pure. |
| | `test_binary_path_uses_shutil_which_only` | `monkeypatch shutil.which`; asserts no other probing, no execution. |
| | `test_installed_engines_never_executes` | `monkeypatch subprocess` attributes to raise; asserts untouched. |
| `test_embed.py` | `test_embedding_target_from_recorded_show` | Recorded fixture. |
| | `test_dimensions_from_model_info_embedding_length` | Pure: `qwen3.embedding_length` → `1024`. |
| | `test_context_length_lands_in_extra` | Pure: `40960`. |
| | `test_mlx_lm_has_no_embeddings_endpoint` | Pure: raises per §11.2. |
| | `test_embed_never_posts_an_inference_request` | Call log has no request to any `/embeddings` path. |
| `test_async_parity.py` | `test_public_api_parity` | Reflection over `__all__`: every sync public callable has an `a`-twin with an identical signature. |
| | `test_aresolve_matches_resolve` | `asyncio.run` + the same fake transport. |
| | `test_aresolve_shares_the_cache` | Counting transport across one sync and one async call. |

---

## 13. LOC budget

A prior extraction in this repo grew **55%** past its pre-split size in five months
(`agent.py` split 8,915 → 5,030 on 2026-04-01; the two halves total 13,852 today). Budgets
are therefore enforced by `test_sloc_ceiling` (non-blank, non-comment lines), not suggested.

| Module | Estimate | Ceiling |
|---|---|---|
| `__init__.py` | 60 | 90 |
| `capabilities.py` | 150 | 200 |
| `quirktable.py` | 200 (mostly data) | 260 |
| `discover.py` | 220 | 300 |
| `target.py` | 180 | 240 |
| `manage.py` | 120 | 160 |
| `embed.py` | 90 | 120 |
| **package total** | **1020** | **1150** |

Per-file ceilings sum to 1370, but the **package** ceiling of 1150 binds first — one module
may grow only if another shrinks. Raising a ceiling requires editing this document in the same
commit. Exceeding it is a failing test, not a review comment.

---

## 14. Worked examples

### (a) Only Ollama running — `Agent(llm="local")`

```python
from praisonaiagents import Agent
agent = Agent(instructions="Summarise this", llm="local")
# integration site calls: local.resolve("local")
```

Four loopback requests (~6 ms on this machine): `GET /` → `Ollama is running`;
`GET /api/version`; `GET /api/tags`; `POST /api/show {"model":"qwen3:0.6b"}`.

Model choice: two models present, so §8.3 rule 4 applies — `qwen3:0.6b` reports
`["completion","tools","thinking"]` while the 9B tamil model reports
`["tools","thinking","completion","vision"]`. Both have `tools`, so the tie-break is
`modified_at` recency, which also selects `qwen3:0.6b`.

```python
LocalTarget(
    engine=LocalEngine.OLLAMA,
    base_url='http://127.0.0.1:11434',
    openai_base_url='http://127.0.0.1:11434/v1',
    api_style=ApiStyle.OPENAI_CHAT,
    model_id='qwen3:0.6b',
    caps=frozenset({Cap.CHAT, Cap.COMPLETION, Cap.TOOLS, Cap.THINKING,
                    Cap.STREAMING, Cap.JSON_OBJECT, Cap.JSON_SCHEMA,
                    Cap.EMBEDDINGS_ENDPOINT}),
    quirks=frozenset({Quirk.FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE,
                      Quirk.TOOL_SCHEMA_KEYWORDS_STRIPPED,
                      Quirk.TOOL_PARAM_TYPE_MUST_BE_BARE_STRING,
                      Quirk.UNKNOWN_OPTIONS_ACCEPTED_AND_IGNORED,
                      Quirk.THINK_FIELD_IGNORED_ON_OPENAI_ROUTE,
                      Quirk.THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN,
                      Quirk.TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL,
                      Quirk.STREAM_ERROR_ENDS_WITHOUT_DONE,
                      Quirk.SAMPLING_DEFAULTS_FORCED_TO_ONE,
                      Quirk.CONTEXT_OPTION_CHANGE_RELOADS_MODEL,
                      Quirk.KEEP_ALIVE_IS_GLOBAL_LAST_WRITER_WINS,
                      Quirk.BODYLESS_403_ON_NON_LOCAL_HOST_HEADER}),
    litellm_model='ollama/qwen3:0.6b',
    api_key='local',
    engine_version='0.33.2',
    evidence=(('api_style', Evidence.TABLE), ('base_url', Evidence.SERVER),
              ('caps', Evidence.SERVER), ('engine', Evidence.SERVER),
              ('engine_version', Evidence.SERVER), ('model_id', Evidence.SERVER),
              ('quirks', Evidence.TABLE)),
    extra=(('context_length', '40960'), ('embedding_length', '1024'),
           ('family', 'qwen3'), ('parameter_size', '751.63M'),
           ('quantization_level', 'Q4_K_M')),
    probed_at=1788439200.0,
)
```

`NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON` is **absent** — `api_style` is `OPENAI_CHAT` and
that quirk is native-route-only. `Cap.VISION` is **absent** — `qwen3:0.6b` reports no vision
(verified twice; vision belongs to the other installed model).
`Cap.STREAMING_WITH_TOOLS` is absent because `TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL` is present.

### (b) `Agent(llm="ollama/qwen3:0.6b")` with `OLLAMA_HOST=127.0.0.1`

Step 1 pins `engine=OLLAMA` and `model_id` (`Evidence.SPEC`); step 3 supplies the base URL —
`parse_ollama_host("127.0.0.1")` → `http://127.0.0.1:11434` (bare host ⇒ 11434). Three
requests: `GET /`, `GET /api/version`, `POST /api/show`. `/api/tags` is **not** fetched
because the model was named.

Result identical to (a) except:
```python
evidence=(('api_style', Evidence.TABLE), ('base_url', Evidence.ENV),
          ('caps', Evidence.SERVER), ('engine', Evidence.SPEC),
          ('engine_version', Evidence.SERVER), ('model_id', Evidence.SPEC),
          ('quirks', Evidence.TABLE)),
```

Had the user written `OLLAMA_HOST=http://127.0.0.1` (explicit scheme, no port ⇒ **port 80**),
step 3 is authoritative and nothing answers on 80:

```
EngineUnreachableError: Local runtime at http://127.0.0.1:80 did not answer (refused). It was named explicitly by OLLAMA_HOST='http://127.0.0.1', so no other port was probed. Note that OLLAMA_HOST with an explicit http:// scheme and no port means port 80, not 11434.
```

It does **not** quietly fall back to 11434.

### (c) Nothing running

Six ports across four numbers probed concurrently; all refused within ~2 ms.

```
NoLocalEngineError: No local model runtime found. Probed 127.0.0.1 ports 11434 (ollama), 8080 (llama_cpp, mlx_lm), 1234 (lm_studio), 8000 (vllm, transformers_serve) in 1.5s; nothing answered. Start one (e.g. `ollama serve`, then `ollama pull qwen3:0.6b`) or set PRAISONAI_LOCAL_BASE_URL to its address.
```

The negative is cached for 5 s, so a loop constructing 100 agents pays the probe cost once.
`local.resolve_or_none("local")` returns `None` instead. `local.remedies(kind=RemedyKind.INSTALL)`
supplies the `argv` a CLI can print — `local/` neither runs it nor formats it for a terminal.

---

## 15. Integration points

Named only. This document designs **no** changes to these sites; each is a separate work order
with its own review. Line numbers are against `main` @ `2591aa405`.

| # | Call site | What it reads from `LocalTarget` |
|---|---|---|
| 15.1 | `agent/agent.py:305-345` — `_PROVIDER_DEFAULT_MODELS` / `_resolve_default_model()` | `litellm_model`. Today hardcodes `("OLLAMA_HOST", "ollama/llama3.2")` — a model that need not be pulled. |
| 15.2 | `agent/agent.py:2049-2112` — `base_url`/`api_key` plumbing | `openai_base_url`, `api_key`, `litellm_model` |
| 15.3 | `agent/agent.py:373` — `_apply_default_llm` base_url path | `openai_base_url` |
| 15.4 | `llm/llm.py:621` — `_detect_provider()` | `engine` (replaces prefix guessing) |
| 15.5 | `llm/llm.py:701` — `_is_ollama_provider()` | `engine` |
| 15.6 | `llm/adapters/__init__.py` — `get_provider_adapter()`, `OllamaAdapter` | `quirks`, `caps` |
| 15.7 | `llm/adapters/__init__.py` — `OllamaAdapter.get_default_settings()` + `llm/llm.py:273` | `quirks` |
| 15.8 | `llm/streaming_protocol.py:285-372` — `OllamaStreamingAdapter` | `TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL`, `STREAM_ERROR_ENDS_WITHOUT_DONE` |
| 15.9 | `llm/model_capabilities.py:106/141/173/204` | `caps` — litellm's map has no entry for a local tag, so these fall to name heuristics today |
| 15.10 | `llm/openai_client.py:645-660` — `_supports_responses_api` | `engine`, `api_style` |
| 15.11 | `llm/model_providers.py:_BUILTINS["ollama"]` | `engine` |
| 15.12 | `llm/sanitize.py`, `agent/chat_mixin.py:690-720` | `TOOL_SCHEMA_KEYWORDS_STRIPPED`, `TOOL_PARAM_TYPE_MUST_BE_BARE_STRING`, `FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE` |
| 15.13 | `tools/call_executor.py:125,141,256,294,351,364` — the `is_ollama: bool` field | `engine` |
| 15.14 | `embedding/embed.py:13` — `embedding()` | `EmbeddingTarget.litellm_model`, `.endpoint`, `.dimensions` |
| 15.15 | `runtime/health_check.py`, `runtime/doctor_registry.py` | `LocalTarget.as_dict()`, `manage.remedies()` |
| 15.16 | `llm/failover.py`, `llm/model_router.py` | `caps` — to avoid routing a tool call to a model without `Cap.TOOLS` |

---

## 16. Non-goals

Each with the reason, so a later contributor does not "add the obvious missing feature".

1. **Not an HTTP client for inference.** litellm and `openai` own that transport; a second one doubles the streaming bug surface.
2. **No chat, completion or embedding inference calls.** Any request whose reply depends on model weights is out. Metadata only.
3. **No process management.** Never starts, stops, restarts or pulls. Returns `argv` for someone else. Starting a server is a privileged side effect with no correct default.
4. **No request mutation, no schema rewriting.** Stripping a `oneOf` for Ollama is behaviour and belongs in `llm/adapters/`; `local/` only says the stripping will happen.
5. **No retries, no backoff, no circuit breaking.** `llm/retry_utils.py`, `llm/rate_limiter.py` and `llm/failover.py` exist; a second policy would silently compete.
6. **No disk cache, no config file.** Persistent state goes stale across `ollama pull`, needs locking, and is behaviour.
7. **No LAN or subnet scanning.** Loopback and explicitly-named hosts only. Sweeping a subnet is a security event, not a feature.
8. **No credential handling.** `api_key` is the fixed placeholder `"local"`; a server behind real auth is named explicitly by the caller.
9. **No model downloading, quantisation choice or VRAM estimation.** Hardware fit is a separate problem with a separate error surface.
10. **No new dependency and no 18th extra.** See §3.
11. **No cloud-provider detection.** `llm/model_providers.py` owns that; overlapping creates a second source of truth for provider ids.
12. **No top-level export.** Reached as `praisonaiagents.local`; nothing added to `_LAZY_IMPORTS`, so the sink cannot be dragged into the package import graph by an `__init__` edit.
13. **No `praisonaiagents.errors` inheritance.** Would import upward and break §2.1; wrapping is the integration layer's job.
14. **No Pydantic models.** Would add a hard-dependency edge and drag validation behaviour into a data package. Frozen dataclasses only.
15. **No support for engines lacking a verified discriminator.** `LLAMAFILE`, `LOCALAI`, `RAMALAMA` are reachable only via `PRAISONAI_LOCAL_ENGINE` until someone verifies an identity endpoint live. Guessing from port 8080 is the exact mistake this table is designed to avoid.
