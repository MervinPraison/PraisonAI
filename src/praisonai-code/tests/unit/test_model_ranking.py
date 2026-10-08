"""Regression tests for issue #5408 — capability-ranked zero-config default.

The per-provider zero-config default must pick the *best available* (most
capable) model rather than a fixed, often-weak representative like
``gpt-4o-mini``. These tests cover:

1. ``ModelCatalogue.best_available`` ranks a capable model above a ``-mini`` one.
2. ``default_model_for_available_provider`` returns the ranked capable model
   when only ``OPENAI_API_KEY`` is present (not ``gpt-4o-mini``), and keeps the
   provider prefix for prefixed providers (Anthropic).
3. ``ModelCatalogue.refresh`` rebuilds the cache on demand.
4. The catalogue cache lives under the canonical ``~/.praisonai`` home, not the
   legacy ``~/.praison``.
"""

from praisonai_code.llm.catalogue import ModelCatalogue, ModelInfo


def _catalogue_with(models):
    cat = ModelCatalogue()
    cat._models = list(models)
    return cat


def test_best_available_prefers_capable_over_mini():
    cat = _catalogue_with([
        ModelInfo(id="gpt-4o-mini", provider="openai", max_context=128000,
                  supports_tools=True),
        ModelInfo(id="gpt-4o", provider="openai", max_context=128000,
                  supports_tools=True, supports_reasoning=True),
    ])
    assert cat.best_available("openai") == "gpt-4o"


def test_best_available_requires_provider_match():
    cat = _catalogue_with([
        ModelInfo(id="claude-3-5-sonnet-latest", provider="anthropic",
                  max_context=200000, supports_tools=True),
    ])
    assert cat.best_available("openai") is None


def test_rank_models_tool_use_wins_over_bigger_context():
    cat = _catalogue_with([
        ModelInfo(id="big-no-tools", provider="x", max_context=2000000,
                  supports_tools=False),
        ModelInfo(id="smaller-tools", provider="x", max_context=128000,
                  supports_tools=True),
    ])
    ranked = cat.rank_models(provider="x")
    assert ranked[0].id == "smaller-tools"


def test_default_openai_is_capable_not_mini(monkeypatch):
    for var in (
        "MODEL_NAME", "OPENAI_MODEL_NAME", "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
        "COHERE_API_KEY", "OLLAMA_HOST",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    from praisonai_code.llm.env import default_model_for_available_provider

    resolved = default_model_for_available_provider()
    assert resolved != "gpt-4o-mini"
    assert "mini" not in resolved.lower()


def test_default_anthropic_keeps_prefix(monkeypatch):
    for var in (
        "MODEL_NAME", "OPENAI_MODEL_NAME", "OPENAI_API_KEY",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
        "COHERE_API_KEY", "OLLAMA_HOST",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    from praisonai_code.llm.env import default_model_for_available_provider

    resolved = default_model_for_available_provider()
    assert resolved.startswith("anthropic/")
    assert "claude" in resolved.lower()


def test_refresh_rebuilds_and_returns_models(tmp_path):
    cat = ModelCatalogue(cache_dir=tmp_path)
    result = cat.refresh()
    assert isinstance(result, dict)
    assert set(result) >= {"cached", "models"}
    models = result["models"]
    assert isinstance(models, list)
    assert models
    assert all("id" in m for m in models)


def test_refresh_reports_cached_when_written(tmp_path):
    # When litellm loads successfully the cache is written and ``cached`` is
    # True; when it cannot load, the fallback table is returned and ``cached``
    # is False and no cache file is written (no false "cached" report).
    cat = ModelCatalogue(cache_dir=tmp_path)
    result = cat.refresh()
    cache_file = tmp_path / "models.json"
    if result["cached"]:
        assert cache_file.exists()
    else:
        assert not cache_file.exists()


def test_refresh_fallback_not_cached(monkeypatch, tmp_path):
    cat = ModelCatalogue(cache_dir=tmp_path)
    monkeypatch.setattr(cat, "_load_from_litellm", lambda: None)
    result = cat.refresh()
    assert result["cached"] is False
    assert result["models"]
    assert not (tmp_path / "models.json").exists()


def test_cache_dir_is_canonical_home(monkeypatch, tmp_path):
    # Pin PRAISONAI_HOME so the assertion holds regardless of the host's
    # home configuration (a machine with only a legacy ~/.praison would
    # otherwise make the canonical-home check flaky).
    home = tmp_path / ".praisonai"
    monkeypatch.setenv("PRAISONAI_HOME", str(home))
    cat = ModelCatalogue()
    assert ".praison/cache" not in str(cat.cache_dir)
    assert ".praisonai" in str(cat.cache_dir)
