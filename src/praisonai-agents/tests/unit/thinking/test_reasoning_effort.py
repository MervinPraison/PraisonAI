"""
Unit tests for the unified reasoning-effort control (Issue #4452).

Covers the three layers the feature touches:
- Translation helper: a graded effort -> each provider's native request param.
- Agent surface: ``Agent(reasoning_effort=...)`` and the legacy
  ``thinking_budget`` alias both reach the LLM request pipeline.
- Session persistence: the effort round-trips through the session store and is
  restored on resume, mirroring the model-persist precedent (#3685).
"""

import tempfile

import pytest

from praisonaiagents.thinking.effort import (
    resolve_reasoning_params,
    normalize_effort,
    EFFORT_LEVELS,
)


class TestResolveReasoningParams:
    """The graded effort translates to the provider-native parameter."""

    @pytest.mark.parametrize("model", ["gpt-5", "openai/gpt-5", "o3-mini", "o1"])
    def test_openai_reasoning_models_emit_native_effort(self, model):
        assert resolve_reasoning_params("high", model) == {"reasoning_effort": "high"}

    def test_xai_models_emit_native_effort(self):
        assert resolve_reasoning_params("low", "xai/grok-3") == {"reasoning_effort": "low"}

    @pytest.mark.parametrize(
        "model,tokens",
        [
            ("claude-3-7-sonnet", 16000),
            ("anthropic/claude-3-7-sonnet", 16000),
            ("gemini/gemini-2.5-pro", 16000),
        ],
    )
    def test_anthropic_gemini_emit_thinking_budget(self, model, tokens):
        assert resolve_reasoning_params("high", model) == {
            "thinking": {"type": "enabled", "budget_tokens": tokens}
        }

    def test_non_reasoning_model_is_ignored(self):
        assert resolve_reasoning_params("high", "gpt-4o") == {}
        assert resolve_reasoning_params("high", "openai/gpt-4o-mini") == {}

    def test_off_and_unset_are_noops(self):
        assert resolve_reasoning_params("off", "gpt-5") == {}
        assert resolve_reasoning_params(None, "gpt-5") == {}

    def test_legacy_budget_int_normalises_to_level(self):
        # The CLI collapses --thinking to a token budget; the inverse mapping
        # recovers the graded level so native reasoning_effort stays graded.
        assert resolve_reasoning_params(16000, "gpt-5") == {"reasoning_effort": "high"}
        assert resolve_reasoning_params(8000, "gpt-5") == {"reasoning_effort": "medium"}
        assert resolve_reasoning_params(2000, "gpt-5") == {"reasoning_effort": "minimal"}


class TestNormalizeEffort:
    def test_string_levels(self):
        assert normalize_effort("HIGH") == "high"
        assert normalize_effort("  low ") == "low"
        assert normalize_effort("nonsense") is None

    def test_int_budget_maps_to_nearest_level(self):
        assert normalize_effort(2000) == "minimal"
        assert normalize_effort(5000) == "medium"
        assert normalize_effort(99999) == "high"
        assert normalize_effort(0) is None

    def test_levels_constant(self):
        assert EFFORT_LEVELS == ("off", "minimal", "low", "medium", "high")


class TestAgentSurface:
    """The Agent constructor threads effort into the LLM request pipeline."""

    def _params(self, agent):
        llm = agent.llm_instance
        return llm._build_completion_params(
            messages=[{"role": "user", "content": "hi"}]
        )

    def test_reasoning_effort_reaches_openai_request(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5", reasoning_effort="high")
        assert agent.reasoning_effort == "high"
        assert self._params(agent).get("reasoning_effort") == "high"

    def test_thinking_budget_alias_reaches_request(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5", thinking_budget=8000)
        assert agent.thinking_budget == 8000
        # 8000 -> "medium" native effort.
        assert self._params(agent).get("reasoning_effort") == "medium"

    def test_anthropic_gets_thinking_budget(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(
            instructions="x",
            llm="anthropic/claude-3-7-sonnet",
            reasoning_effort="high",
        )
        params = self._params(agent)
        assert params.get("thinking") == {"type": "enabled", "budget_tokens": 16000}
        assert "reasoning_effort" not in params

    def test_non_reasoning_model_is_noop(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-4o", reasoning_effort="high")
        params = self._params(agent)
        assert "reasoning_effort" not in params
        assert "thinking" not in params

    def test_setter_syncs_llm_init_params(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5", reasoning_effort="off")
        agent.reasoning_effort = "low"
        assert agent._llm_init_params.get("reasoning_effort") == "low"

    def test_setter_updates_cached_llm_after_materialization(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5", reasoning_effort="low")
        # Materialize (cache) the LLM, then change the effort post-construction.
        _ = self._params(agent)
        agent.reasoning_effort = "high"
        # The already-cached LLM must reflect the new effort on the next request.
        assert self._params(agent).get("reasoning_effort") == "high"

    def test_thinking_budget_setter_reaches_request(self):
        # The CLI assigns ``agent.thinking_budget`` AFTER construction (the
        # ``--thinking`` per-invocation override). This must route through the
        # unified effort so the provider request actually carries it — the
        # previous dormant-alias bug (Issue #4452) only stored ``_thinking_budget``
        # and never emitted the native parameter.
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5")
        _ = self._params(agent)  # cache the LLM first
        agent.thinking_budget = 16000  # -> "high"
        assert agent.reasoning_effort == "high"
        assert agent.thinking_budget == 16000
        assert self._params(agent).get("reasoning_effort") == "high"

    def test_thinking_budget_setter_updates_live_instance(self):
        # Build the LLM instance first (as ``.start()`` would), then change the
        # budget: the cached instance must reflect the new effort without a
        # rebuild, so the CLI override is never silently dropped.
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        agent = Agent(instructions="x", llm="openai/gpt-5")
        _ = agent.llm_instance  # force lazy build
        agent.thinking_budget = 4000  # -> "low"
        assert self._params(agent).get("reasoning_effort") == "low"

    def test_int_budget_normalises_to_graded_level_on_property(self):
        pytest.importorskip("litellm")
        from praisonaiagents import Agent

        # Legacy int budget passed via the alias should surface as a graded level
        # on the persisted/queried property (not the raw int).
        agent = Agent(instructions="x", llm="openai/gpt-5", thinking_budget=8000)
        assert agent.reasoning_effort == "medium"


class TestEffortNormalizationNoLLM:
    """Agent effort surface normalises without requiring LLM deps."""

    def test_property_returns_graded_level_from_int(self):
        from praisonaiagents.thinking.effort import normalize_effort

        assert normalize_effort(16000) == "high"
        assert normalize_effort(4000) == "low"


class TestSessionPersistence:
    """Effort round-trips through the store and restores on resume (#3685)."""

    def test_effort_persists_and_restores(self):
        from praisonaiagents.session.store import DefaultSessionStore, SessionData

        store = DefaultSessionStore(session_dir=tempfile.mkdtemp())
        sid = "sess-effort"
        store.update_session_metadata(
            sid, model="openai/gpt-5", reasoning_effort="high"
        )

        assert store.get_session_model(sid) == "openai/gpt-5"
        assert store.get_session_reasoning_effort(sid) == "high"

        data = store._read_session_fresh(sid).to_dict()
        assert data.get("reasoning_effort") == "high"
        restored = SessionData.from_dict(data)
        assert restored.metadata.get("reasoning_effort") == "high"

    def test_unset_effort_returns_none(self):
        from praisonaiagents.session.store import DefaultSessionStore

        store = DefaultSessionStore(session_dir=tempfile.mkdtemp())
        store.update_session_metadata("sess-no-effort", model="openai/gpt-4o")
        assert store.get_session_reasoning_effort("sess-no-effort") is None
