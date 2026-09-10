"""Tests for framework adapter registry helpers."""

import pytest


def test_list_framework_choices_includes_praisonai():
    from praisonai.framework_adapters.registry import list_framework_choices

    choices = list_framework_choices(include_unavailable=True)
    assert "praisonai" in choices


def test_list_available_frameworks_module_helper():
    from praisonai.framework_adapters.registry import list_available_frameworks

    available = list_available_frameworks()
    assert "praisonai" in available


def test_get_install_hint_fallback():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("unknown_framework_xyz")
    assert "unknown_framework_xyz" in hint


def test_get_install_hint_autogen_v4_extra():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("autogen_v4")
    assert "autogen-v4" in hint


def test_get_install_hint_openai_agents_extra():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("openai_agents")
    assert "openai-agents" in hint


def test_get_install_hint_agno_extra():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("agno")
    assert "agno" in hint


def test_get_install_hint_google_adk_extra():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("google_adk")
    assert "google-adk" in hint


def test_get_install_hint_pydantic_ai_extra():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("pydantic_ai")
    assert "pydantic" in hint.lower()


def test_autogen_family_is_router_skips_run_validation():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()
    adapter = registry.create("autogen")
    assert getattr(adapter, "is_router", False) is True


def test_ag2_not_in_default_builtins():
    from praisonai.framework_adapters import registry as registry_module

    assert "ag2" not in registry_module._BUILTIN_ADAPTERS


def test_resolve_or_default_returns_explicit_name():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()
    assert registry.resolve_or_default("crewai") == "crewai"


def test_resolve_or_default_strips_whitespace():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()
    assert registry.resolve_or_default("  autogen  ") == "autogen"


@pytest.mark.parametrize("name", [None, "", "   "])
def test_resolve_or_default_falls_back_to_pick_default(name):
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()
    assert registry.resolve_or_default(name) == registry.pick_default()


def test_resolve_or_default_fallback_when_no_adapter(monkeypatch):
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()

    def _raise():
        raise RuntimeError("no adapter installed")

    monkeypatch.setattr(registry, "pick_default", _raise)
    assert registry.resolve_or_default(None) == registry.DEFAULT_PRIORITY[0]


def test_framework_from_config_uses_registry_default():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry
    from praisonai.framework_adapters.workflow_framework import framework_from_config

    registry = FrameworkAdapterRegistry()
    assert framework_from_config({}, registry=registry) == registry.pick_default().lower()
    assert framework_from_config({"framework": "CrewAI"}, registry=registry) == "crewai"
