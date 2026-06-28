"""Tests for framework adapter registry helpers."""

import pytest


def test_list_framework_choices_includes_praisonai():
    from praisonai.framework_adapters.registry import list_framework_choices

    choices = list_framework_choices(include_unavailable=True)
    assert "praisonai" in choices


def test_get_install_hint_fallback():
    from praisonai.framework_adapters.registry import get_install_hint

    hint = get_install_hint("unknown_framework_xyz")
    assert "unknown_framework_xyz" in hint


def test_autogen_family_is_router_skips_run_validation():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    registry = FrameworkAdapterRegistry()
    adapter = registry.create("autogen")
    assert getattr(adapter, "is_router", False) is True


def test_ag2_not_in_default_builtins():
    from praisonai.framework_adapters.registry import get_default_registry

    registry = get_default_registry()
    assert "ag2" not in registry.list_names()
