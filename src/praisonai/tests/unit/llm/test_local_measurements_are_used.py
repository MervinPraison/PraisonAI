"""The local layer measures things; these tests prove the measurements are used.

A competitor review found PraisonAI's local *sensing* to be the strongest of five
frameworks and its local *acting* the weakest: capabilities, context windows,
embedding widths and 18 documented quirks were all measured and then discarded.
Each test here pins one measurement to the behaviour it now drives.
"""

import pytest

from praisonaiagents.local.capabilities import ApiStyle, Evidence, LocalEngine
from praisonaiagents.local.discover import Discovery
from praisonaiagents.local.target import build_target


def _target(engine="ollama", base="http://127.0.0.1:11434", extra=()):
    d = Discovery(engine=LocalEngine(engine), base_url=base, api_style=ApiStyle.OPENAI_CHAT,
                  engine_version=None, models=("m",), raw_identity="", latency_ms=1,
                  blocked=None, evidence=Evidence.SERVER)
    return build_target(d, "m", extra=extra) if extra else build_target(d, "m")


class TestContextWindowComesFromTheServer:
    """Compaction budgeted every local model at the generic 128000 default."""

    def test_a_probed_window_beats_the_generic_default(self):
        from praisonaiagents.context.budgeter import get_model_limit
        from praisonaiagents.local.embed import remember_model_facts
        remember_model_facts("tiny-ctx-model", context_length=4096)
        assert get_model_limit("tiny-ctx-model") == 4096, (
            "a 4096-token model still budgeted at the 128000 default would have "
            "31x its real room and the server would truncate silently"
        )

    def test_a_provider_prefixed_name_still_matches(self):
        from praisonaiagents.context.budgeter import get_model_limit
        from praisonaiagents.local.embed import remember_model_facts
        remember_model_facts("prefixed-model", context_length=8192)
        assert get_model_limit("ollama/prefixed-model") == 8192

    def test_an_unprobed_model_is_untouched(self):
        from praisonaiagents.context.budgeter import get_model_limit
        assert get_model_limit("gpt-4o") == 128000


class TestEmbeddingWidthIsCarried:
    """A store built at the wrong width rejects every write or corrupts silently."""

    def test_a_probed_width_reaches_the_embedder_config(self):
        from praisonaiagents.local.embed import local_embedder_config, remember_model_facts
        remember_model_facts("some-embedder", embedding_dimension=768)
        cfg = local_embedder_config(LocalEngine.OLLAMA, "http://127.0.0.1:11434", "some-embedder")
        assert cfg["config"]["embedding_dims"] == 768

    def test_an_unknown_width_is_omitted_rather_than_guessed(self):
        from praisonaiagents.local.embed import local_embedder_config
        cfg = local_embedder_config(LocalEngine.OLLAMA, "http://127.0.0.1:11434", "never-probed")
        assert "embedding_dims" not in cfg["config"], (
            "guessing a width is worse than letting the store infer it"
        )


class TestToolSchemaIsMadeServerSafe:
    """`Optional[str]` produces a union type, which 400s the WHOLE request."""

    UNION_TOOL = [{
        "type": "function",
        "function": {"name": "f", "parameters": {
            "type": "object",
            "properties": {"city": {"type": ["string", "null"]},
                           "nested": {"type": "object",
                                      "properties": {"n": {"type": ["integer", "null"]}}}},
        }},
    }]

    @pytest.mark.parametrize("model", ["ollama/qwen3:0.6b", "lm_studio/x", "vllm/x"])
    def test_local_engines_get_a_bare_type(self, model, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.llm import LLM
        out = LLM(model=model)._format_tools_for_litellm(self.UNION_TOOL)
        props = out[0]["function"]["parameters"]["properties"]
        assert props["city"]["type"] == "string"
        assert props["nested"]["properties"]["n"]["type"] == "integer", "nested unions too"

    def test_hosted_providers_keep_the_full_schema(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.llm import LLM
        out = LLM(model="gpt-4o")._format_tools_for_litellm(self.UNION_TOOL)
        assert out[0]["function"]["parameters"]["properties"]["city"]["type"] == ["string", "null"]

    def test_the_transform_does_not_mutate_the_caller_s_tools(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        from praisonaiagents.llm.adapters import collapse_union_param_types
        original = [{"function": {"parameters": {"properties": {"c": {"type": ["string", "null"]}}}}}]
        collapse_union_param_types(original)
        assert original[0]["function"]["parameters"]["properties"]["c"]["type"] == ["string", "null"]


class TestFormatAndToolsAreRefused:
    """Measured: together, the tool call vanishes and the model invents an answer."""

    TOOLS = [{"type": "function", "function": {"name": "f",
                                               "parameters": {"type": "object", "properties": {}}}}]
    FORMAT = {"type": "json_object"}

    def _params(self, model, **kw):
        from praisonaiagents.llm.llm import LLM
        return LLM(model=model)._build_completion_params(
            messages=[{"role": "user", "content": "x"}], **kw)

    def test_the_combination_raises_on_a_local_engine(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        with pytest.raises(ValueError, match="fabricates"):
            self._params("ollama/qwen3:0.6b", tools=self.TOOLS, response_format=self.FORMAT)

    @pytest.mark.parametrize("kw", [{"tools": TOOLS}, {"response_format": FORMAT}])
    def test_either_alone_is_fine(self, kw, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        assert self._params("ollama/qwen3:0.6b", **kw)

    def test_hosted_providers_may_combine_them(self, monkeypatch):
        """OpenAI honours both together; the refusal must not leak to them."""
        monkeypatch.setenv("OPENAI_API_KEY", "x")
        assert self._params("gpt-4o", tools=self.TOOLS, response_format=self.FORMAT)


class TestLocallyServedEmbedderWidths:
    """Nine local embedders silently inherited OpenAI's 1536.

    Harmless while nothing read the value; wrong the moment it sizes a store.
    """

    @pytest.mark.parametrize("model,width", [
        ("nomic-embed-text", 768), ("mxbai-embed-large", 1024), ("all-minilm", 384),
        ("bge-m3", 1024), ("bge-large", 1024), ("bge-base", 768), ("bge-small", 384),
        ("snowflake-arctic-embed", 1024), ("granite-embedding", 384),
        ("paraphrase-multilingual", 768), ("qwen3-embedding", 1024),
    ])
    def test_a_local_embedder_reports_its_real_width(self, model, width):
        from praisonaiagents.embedding.dimensions import get_dimensions
        assert get_dimensions(model) == width

    def test_an_unknown_embedder_still_reports_the_default(self):
        """The default must stay, so callers can tell 'unknown' from 'measured'."""
        from praisonaiagents.embedding.dimensions import DEFAULT_DIMENSION, get_dimensions
        assert get_dimensions("a-model-nobody-has-heard-of") == DEFAULT_DIMENSION

    def test_a_guessed_width_is_never_sent_to_the_store(self, monkeypatch):
        """Passing the generic default would size the index wrongly and silently."""
        from praisonaiagents.embedding.dimensions import DEFAULT_DIMENSION
        from praisonaiagents.local.embed import local_embedder_config
        from praisonaiagents.local.capabilities import LocalEngine
        cfg = local_embedder_config(LocalEngine.OLLAMA, "http://127.0.0.1:11434", "unknown-embedder")
        assert cfg["config"].get("embedding_dims") != DEFAULT_DIMENSION
