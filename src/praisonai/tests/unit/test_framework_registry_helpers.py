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


def test_resolve_or_default_uses_registered_default():
    from praisonai.framework_adapters.base import BaseFrameworkAdapter
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    class _DefaultAdapter(BaseFrameworkAdapter):
        name = "default_test_adapter"

        def is_available(self):
            return True

        def run(
            self,
            config,
            llm_config,
            topic,
            *,
            tools_dict=None,
            agent_callback=None,
            task_callback=None,
            cli_config=None,
        ):
            return topic

    registry = FrameworkAdapterRegistry(discover_entry_points=False)
    registry.unregister("praisonai")
    registry.register("default_test_adapter", _DefaultAdapter)

    assert registry.resolve_or_default(None) == "default_test_adapter"
    assert registry.resolve_or_default("explicit") == "explicit"
