"""Local model runtime resolution: what is running, what it can do, what it gets wrong.

Every local runtime worth supporting already speaks OpenAI over HTTP, and litellm
already owns that transport. This package is therefore NOT a transport and NOT a
client. It answers three questions and returns the answers as frozen data:

  1. What is running on this machine?      discover()
  2. What can that model actually do?      capabilities via resolve()
  3. What will it silently get wrong?      quirktable

Two properties are load-bearing and are enforced by tests:

  * It is a dependency sink. Every module here imports only the standard library
    and its siblings -- nothing from praisonaiagents. That is what lets modules
    which currently bypass the LLM layer adopt it without deepening the 26
    mutually-importing subpackage pairs the package already has.

  * It produces data, never behaviour. No chat call, no retry, no request
    mutation, no process management, no disk writes. Compensating behaviour
    belongs in llm/adapters/.
"""

from .capabilities import (ApiStyle, Cap, DEFAULT_CAPS, Evidence, LocalEngine,
                           default_caps, parse_llama_cpp_props,
                           parse_lm_studio_models, parse_ollama_capabilities,
                           parse_openai_models)
from .discover import (DEFAULT_PROBE_TIMEOUT, DEFAULT_TOTAL_BUDGET, Discovery,
                       HttpReply, LOOPBACK_HOST, PROBES, ProbeSpec, Rule, RuleKind,
                       discover, models, probe_endpoint, probe_table)
from .quirktable import (NOTES, Quirk, QuirkNote, Severity, all_notes, note,
                         notes_for, quirks_for, silent_quirks)
from .errors import (EngineUnreachableError, HostHeaderRejectedError,
                     InvalidLocalSpecError, LocalError, ModelNotAvailableError,
                     NoLocalEngineError)
from .target import (DEFAULT_API_KEY, ENV_BASE_URL, ENV_ENGINE, ENV_MODEL,
                     LocalTarget, build_target, litellm_model_for,
                     parse_ollama_host, parse_spec, select_model)
from .resolve import cache_info, clear_cache, resolve, resolve_or_none

__all__ = [
    "LocalEngine", "ApiStyle", "Cap", "Evidence", "Severity", "Quirk",
    "DEFAULT_CAPS", "default_caps", "parse_ollama_capabilities",
    "parse_llama_cpp_props", "parse_lm_studio_models", "parse_openai_models",
    "Discovery", "HttpReply", "ProbeSpec", "Rule", "RuleKind", "PROBES",
    "LOOPBACK_HOST", "DEFAULT_PROBE_TIMEOUT", "DEFAULT_TOTAL_BUDGET",
    "discover", "probe_endpoint", "probe_table", "models",
    "QuirkNote", "NOTES", "note", "all_notes", "notes_for", "quirks_for",
    "silent_quirks",
    "LocalTarget", "resolve", "resolve_or_none", "build_target",
    "litellm_model_for", "parse_spec", "parse_ollama_host", "select_model",
    "clear_cache", "cache_info", "DEFAULT_API_KEY", "ENV_BASE_URL", "ENV_ENGINE",
    "ENV_MODEL",
    "LocalError", "NoLocalEngineError", "EngineUnreachableError",
    "HostHeaderRejectedError", "ModelNotAvailableError", "InvalidLocalSpecError",
]
