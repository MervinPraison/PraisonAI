"""Resolution precedence, failure semantics and caching -- all offline.

Every test injects a transport. The autouse `no_sockets` fixture in conftest
turns a forgotten injection into a loud failure rather than a silent hit on
whatever the developer has running.
"""

import pytest

from praisonaiagents.local import (ApiStyle, Cap, EngineUnreachableError, Evidence,
                                   HostHeaderRejectedError, HttpReply,
                                   InvalidLocalSpecError, LocalEngine,
                                   ModelNotAvailableError, NoLocalEngineError,
                                   Quirk, cache_info, clear_cache, discover,
                                   litellm_model_for, parse_ollama_host, parse_spec,
                                   probe_endpoint, resolve, resolve_or_none)
from .conftest import Recorder, ok, text

pytestmark = pytest.mark.unit

OLLAMA_ROUTES = {
    ("GET", "/"): text("Ollama is running"),
    ("GET", "/api/version"): ok({"version": "0.33.2"}),
    ("GET", "/api/tags"): ok({"models": [
        {"model": "qwen3:0.6b", "capabilities": ["completion", "tools", "thinking"],
         "modified_at": "2026-09-03T13:44:23Z"},
        {"model": "nomic-embed-text:latest", "capabilities": ["embedding"],
         "modified_at": "2026-09-03T18:11:39Z"},
    ]}),
    ("POST", "/api/show"): ok({
        "capabilities": ["completion", "tools", "thinking"],
        "details": {"family": "qwen3", "parameter_size": "751.63M"},
        "model_info": {"qwen3.context_length": 40960, "qwen3.embedding_length": 1024},
    }),
}


def ollama(extra=None):
    routes = dict(OLLAMA_ROUTES)
    routes.update(extra or {})
    return Recorder(routes)


# --- identity is never inferred from a port ----------------------------------

def test_ollama_identified_by_body_not_port():
    t = ollama()
    found = probe_endpoint("http://127.0.0.1:11434", transport=t)
    assert found.engine is LocalEngine.OLLAMA
    assert found.engine_version == "0.33.2"


def test_something_else_on_11434_is_not_ollama():
    """A server answering 200 on Ollama's port is UNKNOWN, not Ollama."""
    t = Recorder({("GET", "/"): text("hello there")})
    found = probe_endpoint("http://127.0.0.1:11434", transport=t)
    assert found.engine is LocalEngine.UNKNOWN


def test_port_8080_collision_llama_cpp_vs_mlx():
    """Both claim 8080; /props is the discriminator."""
    llama = Recorder({("GET", "/health"): text("ok"),
                      ("GET", "/props"): ok({"build_info": "b7620", "modalities": {}})})
    assert probe_endpoint("http://127.0.0.1:8080", transport=llama).engine is LocalEngine.LLAMA_CPP

    mlx = Recorder({("GET", "/health"): text("ok"),
                    ("GET", "/props"): HttpReply(404, b"nope"),
                    ("GET", "/v1/models"): ok({"data": [{"id": "mlx-model"}]})})
    assert probe_endpoint("http://127.0.0.1:8080", transport=mlx).engine is LocalEngine.MLX_LM


def test_port_8000_collision_vllm_vs_transformers():
    vllm = Recorder({("GET", "/version"): ok({"version": "0.28.0"})})
    assert probe_endpoint("http://127.0.0.1:8000", transport=vllm).engine is LocalEngine.VLLM

    tf = Recorder({("GET", "/version"): HttpReply(404, b""),
                   ("GET", "/health"): text("ok"),
                   ("GET", "/v1/models"): ok({"data": [{"id": "hf-model"}]})})
    assert probe_endpoint("http://127.0.0.1:8000", transport=tf).engine is LocalEngine.TRANSFORMERS_SERVE


# --- failure semantics --------------------------------------------------------

def test_refused_yields_nothing_and_does_not_raise():
    assert probe_endpoint("http://127.0.0.1:11434", transport=Recorder({})) is None
    assert discover(transport=Recorder({})) == ()


def test_bodyless_403_is_reported_not_hidden():
    """Ollama's Host-header rejection must not look like 'nothing is running'."""
    t = Recorder({}, default=HttpReply(403, b"", "http"))
    found = probe_endpoint("http://192.168.1.10:11434", transport=t)
    assert found is not None and found.blocked == "host_header_rejected"


def test_blocked_only_raises_host_header_error(monkeypatch):
    monkeypatch.setenv("PRAISONAI_LOCAL_BASE_URL", "http://192.168.1.10:11434")
    t = Recorder({}, default=HttpReply(403, b"", "http"))
    with pytest.raises(HostHeaderRejectedError) as exc:
        resolve(transport=t)
    assert "Host header" in str(exc.value)


def test_malformed_json_does_not_raise():
    t = ollama({("GET", "/api/tags"): text("{not json")})
    found = probe_endpoint("http://127.0.0.1:11434", transport=t)
    assert found.engine is LocalEngine.OLLAMA
    assert found.models == ()


def test_nothing_running_names_what_was_probed():
    with pytest.raises(NoLocalEngineError) as exc:
        resolve("local", transport=Recorder({}))
    msg = str(exc.value)
    assert "11434 (ollama)" in msg and "8080" in msg and "PRAISONAI_LOCAL_BASE_URL" in msg


def test_resolve_or_none_swallows():
    assert resolve_or_none("local", transport=Recorder({})) is None


# --- precedence ---------------------------------------------------------------

def test_named_source_that_does_not_answer_raises_without_falling_back(monkeypatch):
    """Silently using a different server than the caller named is the failure
    mode this package exists to prevent."""
    monkeypatch.setenv("PRAISONAI_LOCAL_BASE_URL", "http://127.0.0.1:9999")
    t = Recorder(OLLAMA_ROUTES)   # would answer, but only on the path it is asked
    t.routes = {}                  # nothing answers at all
    with pytest.raises(EngineUnreachableError) as exc:
        resolve(transport=t)
    assert exc.value.source == "PRAISONAI_LOCAL_BASE_URL"
    assert "9999" in str(exc.value)


def test_ollama_host_scheme_asymmetry_is_reported(monkeypatch):
    """http:// with no port means 80, not 11434 -- users trip on this."""
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1")
    with pytest.raises(EngineUnreachableError) as exc:
        resolve(transport=Recorder({}))
    assert ":80" in str(exc.value)
    assert "not 11434" in str(exc.value)


@pytest.mark.parametrize("value, expected", [
    ("127.0.0.1", "http://127.0.0.1:11434"),
    ("127.0.0.1:11500", "http://127.0.0.1:11500"),
    ("11500", "http://127.0.0.1:11500"),
    (":11500", "http://127.0.0.1:11500"),
    ("http://127.0.0.1", "http://127.0.0.1:80"),
    ("https://example.com", "https://example.com:443"),
    ("", None),
])
def test_parse_ollama_host(value, expected):
    assert parse_ollama_host(value) == expected


def test_non_local_openai_base_url_is_ignored(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    with pytest.raises(NoLocalEngineError) as exc:
        resolve("local", transport=Recorder({}))
    assert "not a local address" in str(exc.value)


def test_spec_engine_prefix_pins_the_engine(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    t = ollama()
    target = resolve("ollama/qwen3:0.6b", transport=t)
    assert target.model_id == "qwen3:0.6b"
    assert target.evidence_for("model_id") is Evidence.SPEC
    assert target.evidence_for("base_url") is Evidence.ENV


def test_bad_spec_raises():
    with pytest.raises(InvalidLocalSpecError):
        parse_spec("!!! not a spec !!!")


# --- model selection ----------------------------------------------------------

def test_embedding_only_model_is_never_chosen_to_chat(monkeypatch):
    """The listing's newest entry is an embedder; it must not win."""
    t = ollama({("GET", "/api/tags"): ok({"models": [
        {"model": "aaa-embed", "capabilities": ["embedding"],
         "modified_at": "2026-09-03T23:00:00Z"},
        {"model": "zzz-chat", "capabilities": ["completion", "tools"],
         "modified_at": "2026-01-01T00:00:00Z"},
    ]})})
    assert resolve("local", transport=t).model_id == "zzz-chat"


def test_named_model_not_served_lists_alternatives(monkeypatch):
    monkeypatch.setenv("PRAISONAI_LOCAL_MODEL", "llama3.2")
    with pytest.raises(ModelNotAvailableError) as exc:
        resolve("local", transport=ollama())
    assert "qwen3:0.6b" in str(exc.value)


def test_explicit_spec_model_not_served_raises_at_resolution(monkeypatch):
    """A spec-named model absent from the server must fail here, not on the
    first completion; Agent would otherwise send an unavailable id to Ollama."""
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    with pytest.raises(ModelNotAvailableError) as exc:
        resolve("ollama/does-not-exist", transport=ollama())
    assert "does-not-exist" in str(exc.value)
    assert "qwen3:0.6b" in str(exc.value)


def test_reachable_server_with_no_models_raises(monkeypatch):
    """A server that answers but lists no model must not yield a model-less
    target -- Agent would then substitute its own default (e.g. gpt-4o-mini)
    and send it to the local endpoint."""
    t = ollama({("GET", "/api/tags"): ok({"models": []})})
    with pytest.raises(NoLocalEngineError) as exc:
        resolve("local", transport=t)
    assert "no usable model" in str(exc.value)


# --- the produced target ------------------------------------------------------

def test_target_carries_capabilities_and_quirks_from_the_server():
    target = resolve("local", transport=ollama())
    assert target.supports(Cap.TOOLS) and target.supports(Cap.THINKING)
    assert target.evidence_for("caps") is Evidence.SERVER
    assert target.has_quirk(Quirk.FORMAT_AND_TOOLS_MUTUALLY_DESTRUCTIVE)
    # OPENAI_CHAT route, so the native-only quirk must be absent
    assert not target.has_quirk(Quirk.NATIVE_ROUTE_NEVER_SETS_TOOL_FINISH_REASON)
    assert target.get_extra("context_length") == "40960"


def test_target_is_frozen_and_hashable():
    target = resolve("local", transport=ollama())
    hash(target)
    with pytest.raises(Exception):
        target.model_id = "other"


def test_as_dict_is_json_serialisable():
    import json
    json.dumps(resolve("local", transport=ollama()).as_dict())


@pytest.mark.parametrize("engine, expected", [
    (LocalEngine.OLLAMA, "ollama/m"),
    (LocalEngine.LM_STUDIO, "lm_studio/m"),
    (LocalEngine.VLLM, "hosted_vllm/m"),
    (LocalEngine.MLX_LM, "openai/m"),
    (LocalEngine.UNKNOWN, "openai/m"),
])
def test_litellm_model_for(engine, expected):
    assert litellm_model_for(engine, "m") == expected


def test_ollama_never_maps_to_ollama_chat():
    """_detect_provider resolves ollama_chat to 'openai' and would lose the adapter."""
    assert litellm_model_for(LocalEngine.OLLAMA, "m") == "ollama/m"


# --- caching ------------------------------------------------------------------

def test_second_resolve_does_not_reprobe():
    t = ollama()
    resolve("local", transport=t)
    before = len(t.calls)
    resolve("local", transport=t)
    assert len(t.calls) == before


def test_refresh_bypasses_cache():
    t = ollama()
    resolve("local", transport=t)
    before = len(t.calls)
    resolve("local", transport=t, refresh=True)
    assert len(t.calls) > before


def test_env_change_is_a_cache_miss(monkeypatch):
    t = ollama()
    resolve("local", transport=t)
    before = len(t.calls)
    monkeypatch.setenv("PRAISONAI_LOCAL_MODEL", "qwen3:0.6b")
    resolve("local", transport=t)
    assert len(t.calls) > before


def test_negative_result_is_cached_and_reraised_fresh():
    t = Recorder({})
    with pytest.raises(NoLocalEngineError) as first:
        resolve("local", transport=t)
    probes = len(t.calls)
    with pytest.raises(NoLocalEngineError) as second:
        resolve("local", transport=t)
    assert len(t.calls) == probes           # no second probe round
    assert first.value is not second.value  # a fresh instance, not a stored one
    assert str(first.value) == str(second.value)


def test_clear_cache_empties_both():
    resolve("local", transport=ollama())
    clear_cache()
    info = cache_info()
    assert info["targets"] == 0 and info["negatives"] == 0
