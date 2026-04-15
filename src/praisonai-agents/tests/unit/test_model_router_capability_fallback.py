from praisonaiagents.llm.model_router import ModelRouter


def test_select_compatible_fallback_keeps_preferred_when_compatible():
    router = ModelRouter()

    selected = router.select_compatible_fallback(
        preferred_model="gpt-4o-mini",
        required_capabilities=["text", "function-calling"],
        context_size=1024,
    )

    assert selected == "gpt-4o-mini"


def test_select_compatible_fallback_switches_on_missing_vision():
    router = ModelRouter()

    selected = router.select_compatible_fallback(
        preferred_model="deepseek-chat",
        required_capabilities=["text", "vision"],
        context_size=1024,
    )

    assert selected != "deepseek-chat"

    profile = router.get_model_info(selected)
    assert profile is not None
    assert "vision" in profile.capabilities


def test_select_compatible_fallback_respects_context_window():
    router = ModelRouter()

    selected = router.select_compatible_fallback(
        preferred_model="gpt-4o-mini",
        required_capabilities=["text"],
        context_size=1_500_000,
    )

    profile = router.get_model_info(selected)
    assert profile is not None
    assert profile.context_window >= 1_500_000
