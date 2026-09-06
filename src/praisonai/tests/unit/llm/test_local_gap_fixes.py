"""Regressions for gaps found by auditing the merged local-model work.

Each test names the defect it guards. All are offline: they use a fake HTTP
transport or pure functions, so they pass with no server and no keys.
"""

import pytest

from praisonaiagents import local
from praisonaiagents.local.capabilities import ApiStyle, Evidence, LocalEngine
from praisonaiagents.local.discover import Discovery, HttpReply


def _transport(routes, default=HttpReply(0, b"", "refused")):
    """Fake Transport: routes is {(method, path): HttpReply}."""
    def send(method, url, body, timeout):
        path = url.split("://", 1)[1].split("/", 1)
        path = "/" + path[1] if len(path) > 1 else "/"
        return routes.get((method, path), default)
    return send


class TestDiscoveryFallback:
    """S2: a live OpenAI-compatible server that 404s '/' was reported absent."""

    OPENAI_ONLY = {
        ("GET", "/v1/models"): HttpReply(200, b'{"object":"list","data":[{"id":"m1"}]}', None),
    }

    def test_a_server_that_only_answers_v1_models_is_found(self):
        d = local.probe_endpoint("http://127.0.0.1:9", transport=_transport(
            self.OPENAI_ONLY, default=HttpReply(404, b"{}", "http")))
        assert d is not None, "a live OpenAI-compatible server was reported absent"
        assert d.engine is LocalEngine.UNKNOWN
        assert d.models == ("m1",)

    def test_a_genuinely_dead_host_is_still_absent(self):
        # The fallback must not turn a transport failure into a discovery.
        assert local.probe_endpoint("http://127.0.0.1:9", transport=_transport({})) is None

    def test_a_base_already_ending_in_v1_is_not_doubled(self):
        """LM Studio and vLLM print a base ending in /v1; the fallback probe
        appended /v1/models, producing /v1/v1/models -> a 404 that made a live
        server look absent."""
        d = local.probe_endpoint("http://127.0.0.1:9/v1", transport=_transport(
            {("GET", "/v1/models"): HttpReply(
                200, b'{"object":"list","data":[{"id":"m1"}]}', None)},
            default=HttpReply(404, b"{}", "http")))
        assert d is not None, "a /v1 base was probed at /v1/v1/models and looked absent"
        assert d.models == ("m1",)


class TestEnginePin:
    """S3: PRAISONAI_LOCAL_ENGINE only ever filtered, so engines with no
    ProbeSpec (llamafile, localai, ramalama) were reachable by no route."""

    @pytest.mark.parametrize("engine", ["llamafile", "localai", "ramalama"])
    def test_an_engine_without_a_probe_spec_can_still_be_pinned(self, engine):
        d = local.probe_endpoint(
            "http://127.0.0.1:9", expect=engine,
            transport=_transport({("GET", "/v1/models"): HttpReply(
                200, b'{"data":[{"id":"m1"}]}', None)},
                default=HttpReply(404, b"{}", "http")))
        assert d is not None, f"{engine} pinned by env was unreachable"
        assert d.engine is LocalEngine(engine)
        assert d.evidence is Evidence.ENV, "a pinned engine is asserted, not observed"


class TestUrlHandling:
    def test_a_path_prefix_survives(self):
        """A reverse proxy commonly mounts the server under a path."""
        assert local.parse_ollama_host("http://gateway:8000/ollama") == "http://gateway:8000/ollama"

    def test_a_bare_host_still_defaults_to_11434(self):
        assert local.parse_ollama_host("127.0.0.1") == "http://127.0.0.1:11434"

    def test_an_explicit_scheme_without_a_port_still_means_80(self):
        assert local.parse_ollama_host("http://127.0.0.1") == "http://127.0.0.1:80"

    def test_v1_is_not_doubled(self):
        """Users paste the URL their server prints, which often ends in /v1."""
        from praisonaiagents.local.target import _openai_base
        assert _openai_base("http://h:1234/v1") == "http://h:1234/v1"
        assert _openai_base("http://h:11434") == "http://h:11434/v1"


class TestLocalEmbedderSelection:
    """S1: a local agent embedded against OpenAI, sending documents off-machine."""

    META = (
        ("qwen3:0.6b", ("completion", "tools"), "2026-09-03T10:00:00Z"),
        ("all-minilm:latest", ("embedding",), "2026-09-03T10:00:00Z"),
        ("nomic-embed-text:latest", ("embedding",), "2026-09-03T10:00:00Z"),
    )
    NAMES = tuple(m[0] for m in META)

    def test_an_embedding_model_is_preferred_over_a_chat_model(self):
        assert local.select_embedding_model(self.NAMES, self.META) == "nomic-embed-text:latest"

    def test_none_when_the_server_serves_no_embedder(self):
        """Must be None, never a cloud default -- that was the leak."""
        chat_only = (("qwen3:0.6b", ("completion",), None),)
        assert local.select_embedding_model(("qwen3:0.6b",), chat_only) is None

    def test_an_explicit_choice_wins(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_LOCAL_EMBED_MODEL", "all-minilm")
        assert local.select_embedding_model(self.NAMES, self.META) == "all-minilm:latest"

    def test_ollama_embedder_config_carries_the_endpoint(self):
        cfg = local.local_embedder_config(
            LocalEngine.OLLAMA, "http://127.0.0.1:11434", "nomic-embed-text")
        assert cfg["provider"] == "ollama"
        assert cfg["config"]["ollama_base_url"] == "http://127.0.0.1:11434"

    def test_openai_shaped_engines_get_a_v1_endpoint(self):
        cfg = local.local_embedder_config(
            LocalEngine.LM_STUDIO, "http://127.0.0.1:1234", "text-embed")
        assert cfg["config"]["openai_base_url"].endswith("/v1")


class TestChromaAdapterHonoursTheEmbedder:
    """S1 root cause: the adapter read only OPENAI_EMBEDDING_MODEL, so a
    configured local embedder was silently discarded."""

    def _adapter(self, embedder):
        from praisonaiagents.knowledge.adapters.factories import ChromaKnowledgeAdapter
        a = ChromaKnowledgeAdapter.__new__(ChromaKnowledgeAdapter)
        a._embedder = embedder
        return a

    def test_a_configured_ollama_embedder_is_used_with_its_endpoint(self):
        model, kwargs = self._adapter({
            "provider": "ollama",
            "config": {"model": "nomic-embed-text", "ollama_base_url": "http://127.0.0.1:11434"},
        })._embedding_call()
        assert model == "ollama/nomic-embed-text"
        assert kwargs["api_base"] == "http://127.0.0.1:11434"

    def test_no_embedder_configured_falls_back_to_the_previous_default(self):
        model, kwargs = self._adapter({})._embedding_call()
        assert model == "text-embedding-3-small"
        assert kwargs == {}, "an unconfigured call must be byte-identical to before"


class TestLlamaCppPrefixIsRoutable:
    """A prefix we accept must be one litellm can route, or the request dies
    after four retries with 'LLM Provider NOT provided'."""

    @pytest.mark.parametrize("prefix", ["llama_cpp", "llamacpp"])
    def test_llama_cpp_is_rewritten_for_litellm(self, prefix, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model=f"{prefix}/qwen3", base_url="http://127.0.0.1:8080/v1")
        assert llm._resolve_openai_compatible_model() == "openai/qwen3"

    def test_it_still_selects_the_local_adapter(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.adapters import LocalOpenAIAdapter
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="llama_cpp/qwen3", base_url="http://127.0.0.1:8080/v1")
        assert isinstance(llm._provider_adapter, LocalOpenAIAdapter)

    @pytest.mark.parametrize("model", ["ollama/x", "lm_studio/x", "vllm/x", "gpt-4o"])
    def test_other_prefixes_are_untouched(self, model, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model=model)
        resolved = llm._resolve_openai_compatible_model()
        assert resolved == model or resolved == f"openai/{model}"


class TestNonOllamaEndpointGetsV1:
    """S7: every local engine but Ollama serves under /v1.

    Handing an LM Studio / vLLM / llama-server target the bare server root sent
    chat to /chat/completions, which those servers answer with 404. It was
    latent while non-Ollama engines could not be discovered at all; fixing
    discovery made it reachable.
    """

    def _target(self, engine, base="http://127.0.0.1:1234"):
        from praisonaiagents.local.capabilities import ApiStyle, Evidence, LocalEngine
        from praisonaiagents.local.discover import Discovery
        from praisonaiagents.local.target import build_target
        d = Discovery(engine=LocalEngine(engine), base_url=base,
                      api_style=ApiStyle.OPENAI_CHAT, engine_version=None,
                      models=("m",), raw_identity="", latency_ms=1, blocked=None,
                      evidence=Evidence.SERVER)
        return build_target(d, "m")

    @pytest.mark.parametrize("engine", ["lm_studio", "vllm", "llama_cpp", "mlx_lm"])
    def test_openai_shaped_engines_expose_a_v1_root(self, engine):
        t = self._target(engine)
        assert t.openai_base_url == "http://127.0.0.1:1234/v1"

    def test_ollama_keeps_the_bare_root(self):
        """litellm's ollama provider builds its own /api paths from the root."""
        t = self._target("ollama", "http://127.0.0.1:11434")
        assert t.base_url == "http://127.0.0.1:11434"

    def test_agent_hands_non_ollama_the_v1_root(self, monkeypatch):
        from praisonaiagents.local.capabilities import LocalEngine
        target = self._target("lm_studio")
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        monkeypatch.setattr("praisonaiagents.local.resolve", lambda *a, **k: target)
        from praisonaiagents import Agent
        agent = Agent(instructions="x", llm="local")
        assert agent.llm_instance.base_url == "http://127.0.0.1:1234/v1", (
            "a non-Ollama local engine was given the bare root, so chat would "
            "go to /chat/completions and 404"
        )

    def test_agent_hands_ollama_the_bare_root(self, monkeypatch):
        target = self._target("ollama", "http://127.0.0.1:11434")
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        monkeypatch.setattr("praisonaiagents.local.resolve", lambda *a, **k: target)
        from praisonaiagents import Agent
        agent = Agent(instructions="x", llm="local")
        assert agent.llm_instance.base_url == "http://127.0.0.1:11434"
