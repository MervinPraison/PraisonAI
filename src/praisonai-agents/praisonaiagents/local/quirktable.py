"""Static catalogue of local-engine behaviours that fail without an error.

Pure data. No network, no I/O, no environment reads. Every SILENT entry is a way
a local server returns HTTP 200 and a wrong result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from .capabilities import ApiStyle, Cap, LocalEngine

__all__ = ["Severity", "Quirk", "QuirkNote", "NOTES", "note", "all_notes",
           "notes_for", "quirks_for", "silent_quirks"]


class Severity(str, Enum):
    SILENT = "silent"   # wrong result, no error surface -- the dangerous class
    HARD = "hard"       # the request fails loudly (4xx/5xx)
    COST = "cost"       # correct result, unexpected latency or resource cost


class Quirk(str, Enum):
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
    TOOLS_REQUIRE_SERVER_FLAGS = "tools_require_server_flags"
    NO_JSON_SCHEMA_SUPPORT = "no_json_schema_support"
    NO_EMBEDDINGS_ENDPOINT = "no_embeddings_endpoint"
    SINGLE_MODEL_PER_PROCESS = "single_model_per_process"
    CAPS_ASSUMED_ENGINE_UNIDENTIFIED = "caps_assumed_engine_unidentified"


@dataclass(frozen=True)
class QuirkNote:
    quirk: Quirk
    engines: tuple
    severity: Severity
    symptom: str
    workaround: str
    verified_on: str
    api_styles: tuple = ()
    requires_caps: frozenset = field(default_factory=frozenset)


_OLLAMA = (LocalEngine.OLLAMA,)
_OPENAI_ROUTES = (ApiStyle.OPENAI_CHAT, ApiStyle.OPENAI_COMPLETIONS)
_V = "ollama 0.33.2 @ 2026-09-03"

NOTES: Mapping[Quirk, QuirkNote] = {n.quirk: n for n in (
    QuirkNote(
        Quirk.FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE, _OLLAMA, Severity.SILENT,
        "JSON format plus tools suppresses the tool call; the model fabricates an answer.",
        "Refuse the combination at request build. Raise -- a confident fabrication is worse than an error.",
        _V),
    QuirkNote(
        Quirk.TOOL_SCHEMA_KEYWORDS_STRIPPED, _OLLAMA, Severity.SILENT,
        "minLength, format, default, additionalProperties, $ref and oneOf never reach the model.",
        "Warn once at tool-declaration time, naming the dropped keys.", _V),
    QuirkNote(
        Quirk.TOOL_PARAM_TYPE_MUST_BE_BARE_STRING, _OLLAMA, Severity.HARD,
        'A tool parameter "type" given as a list 400s the whole request.',
        "Collapse union types to a single string before sending.", _V),
    QuirkNote(
        Quirk.UNKNOWN_OPTIONS_ACCEPTED_AND_IGNORED, _OLLAMA, Severity.SILENT,
        "Unrecognised options keys return 200 and change nothing.",
        "Validate keys against the known set; warn on unknowns.", _V),
    QuirkNote(
        Quirk.THINK_FIELD_IGNORED_ON_OPENAI_ROUTE, _OLLAMA, Severity.SILENT,
        "think is a native-API field; on /v1 it is dropped and reasoning still emits.",
        'Translate to reasoning_effort="none" on the OpenAI route.', _V,
        api_styles=_OPENAI_ROUTES),
    QuirkNote(
        Quirk.THINKING_WITH_TOOLS_YIELDS_EMPTY_TURN, _OLLAMA, Severity.SILENT,
        'Empty content, zero tool calls, finish_reason "stop".',
        "Treat as retryable; retry once with reasoning disabled.", _V,
        requires_caps=frozenset({Cap.THINKING, Cap.TOOLS})),
    QuirkNote(
        Quirk.NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON, _OLLAMA, Severity.SILENT,
        '/api/chat reports done_reason "stop" even when tool_calls is populated.',
        "Inspect the message body, never the finish reason.", _V,
        api_styles=(ApiStyle.OLLAMA_NATIVE,)),
    QuirkNote(
        Quirk.TOOL_CALLS_ARRIVE_WHOLE_NOT_INCREMENTAL, _OLLAMA, Severity.SILENT,
        "Streamed tool calls arrive in one chunk, not as argument deltas.",
        "The accumulator must tolerate both; never assume fragments.", _V),
    QuirkNote(
        Quirk.STREAM_ERROR_ENDS_WITHOUT_DONE, _OLLAMA, Severity.SILENT,
        "A mid-stream failure yields an empty delta and no [DONE] sentinel.",
        "Set a read timeout; check every NDJSON line for an error key.", _V,
        api_styles=_OPENAI_ROUTES),
    QuirkNote(
        Quirk.SAMPLING_DEFAULTS_FORCED_TO_ONE, _OLLAMA, Severity.SILENT,
        "Omitted temperature/top_p become 1.0, not the model's own defaults.",
        "Send explicit values, or use the native route.", _V,
        api_styles=_OPENAI_ROUTES),
    QuirkNote(
        Quirk.CONTEXT_OPTION_CHANGE_RELOADS_MODEL, _OLLAMA, Severity.COST,
        "Changing num_ctx/num_batch/num_gpu forces a full model reload.",
        "Freeze runner options per target; never vary them per call.", _V),
    QuirkNote(
        Quirk.KEEP_ALIVE_IS_GLOBAL_LAST_WRITER_WINS, _OLLAMA, Severity.SILENT,
        "keep_alive is per-model and process-wide, not per-request.",
        "Never send keep_alive=0 from a library path; it evicts another caller's model.", _V),
    QuirkNote(
        Quirk.BODYLESS_403_ON_NON_LOCAL_HOST_HEADER, _OLLAMA, Severity.HARD,
        "A Host header that is not localhost or an IP gets HTTP 403 with a zero-byte body.",
        "Send Host as localhost or an IP; set OLLAMA_HOST on the server to allow the origin.", _V),
    QuirkNote(
        Quirk.TOOLS_REQUIRE_SERVER_FLAGS,
        (LocalEngine.VLLM, LocalEngine.LLAMA_CPP, LocalEngine.LLAMAFILE), Severity.SILENT,
        "Tool calls come back as assistant text unless the server was launched with the right flags.",
        "vLLM needs BOTH --enable-auto-tool-choice AND --tool-call-parser; llama-server needs --jinja.",
        "unverified: vendor docs"),
    QuirkNote(
        Quirk.NO_JSON_SCHEMA_SUPPORT, (LocalEngine.MLX_LM,), Severity.SILENT,
        "response_format json_schema is unimplemented.",
        "Drop the capability; fall back to prompt-and-parse.", "unverified: source read"),
    QuirkNote(
        Quirk.NO_EMBEDDINGS_ENDPOINT, (LocalEngine.MLX_LM,), Severity.HARD,
        "/v1/embeddings is absent.",
        "Resolve embeddings to a different target, and say so.", "unverified: source read"),
    QuirkNote(
        Quirk.SINGLE_MODEL_PER_PROCESS,
        (LocalEngine.LLAMA_CPP, LocalEngine.MLX_LM), Severity.SILENT,
        "One model per process; the request's model field is ignored.",
        "Asking for model B returns model A's answer. Pin the model at launch.",
        "unverified: vendor docs"),
    QuirkNote(
        Quirk.CAPS_ASSUMED_ENGINE_UNIDENTIFIED, (LocalEngine.UNKNOWN,), Severity.SILENT,
        "The engine could not be identified, so every capability is a static guess.",
        "Treat capabilities as unproven; keep repair paths enabled.", "n/a"),
)}


def note(quirk) -> QuirkNote:
    """Return the catalogue entry for one quirk."""
    return NOTES[Quirk(quirk)]


def all_notes() -> tuple:
    """Every catalogue entry, ordered by (first engine, quirk value)."""
    return tuple(sorted(NOTES.values(), key=lambda n: (n.engines[0].value, n.quirk.value)))


def quirks_for(engine, api_style, *, caps=frozenset()) -> frozenset:
    """Quirks that apply to this engine, route and capability set."""
    engine = LocalEngine(engine)
    style = ApiStyle(api_style)
    caps = frozenset(caps)
    return frozenset(
        n.quirk for n in NOTES.values()
        if engine in n.engines
        and (not n.api_styles or style in n.api_styles)
        and n.requires_caps <= caps
    )


def notes_for(quirks: Iterable) -> tuple:
    """Catalogue entries for ``quirks``, ordered by severity then value."""
    order = {Severity.SILENT: 0, Severity.HARD: 1, Severity.COST: 2}
    got = [NOTES[Quirk(q)] for q in quirks]
    return tuple(sorted(got, key=lambda n: (order[n.severity], n.quirk.value)))


def silent_quirks(quirks: Iterable) -> frozenset:
    """Filter to Severity.SILENT -- the set a caller must actively defend against."""
    return frozenset(q for q in (Quirk(x) for x in quirks) if NOTES[q].severity is Severity.SILENT)
