"""Tests for model-aware runtime profiles."""

import pytest

from praisonaiagents.runtime.profiles import (
    RuntimeProfile,
    RuntimeProfileProtocol,
    RuntimeProfileRegistry,
    resolve_model_family,
    resolve_profile,
    register_profile,
    list_profiles,
    DEFAULT_PROFILE_NAME,
)


class TestResolveModelFamily:
    def test_none_and_empty(self):
        assert resolve_model_family(None) == DEFAULT_PROFILE_NAME
        assert resolve_model_family("") == DEFAULT_PROFILE_NAME

    def test_anthropic(self):
        assert resolve_model_family("claude-3-5-sonnet") == "anthropic"
        assert resolve_model_family("anthropic/claude-3-opus") == "anthropic"

    def test_gemini(self):
        assert resolve_model_family("gemini-1.5-pro") == "gemini"
        assert resolve_model_family("google/gemini-2.0-flash") == "gemini"

    def test_openai(self):
        assert resolve_model_family("gpt-4o") == "openai"
        assert resolve_model_family("openai/gpt-4o-mini") == "openai"
        assert resolve_model_family("o1-preview") == "openai"

    def test_unknown_defaults(self):
        assert resolve_model_family("some-random-model") == DEFAULT_PROFILE_NAME


class TestRuntimeProfile:
    def test_default_is_default(self):
        p = RuntimeProfile()
        assert p.is_default is True
        assert p.name == DEFAULT_PROFILE_NAME

    def test_default_apply_is_noop(self):
        p = RuntimeProfile()
        prompt = "You are a helpful assistant."
        assert p.apply_system_prompt(prompt) == prompt

    def test_family_profile_without_text_is_prompt_neutral(self):
        # Built-in family profiles carry only preferred_edit_format, no prompt
        # text -> prompt-neutral -> byte-for-byte identical prompt output.
        p = RuntimeProfile(name="anthropic", preferred_edit_format="string-replace")
        assert p.is_prompt_neutral is True
        assert p.is_default is False  # carries an edit format
        prompt = "hello"
        assert p.apply_system_prompt(prompt) == prompt

    def test_prefix_and_suffix_applied(self):
        p = RuntimeProfile(
            name="custom",
            system_prompt_prefix="PREFIX",
            system_prompt_suffix="SUFFIX",
        )
        assert p.is_default is False
        result = p.apply_system_prompt("BODY")
        assert result == "PREFIX\n\nBODY\n\nSUFFIX"

    def test_apply_handles_none(self):
        p = RuntimeProfile(system_prompt_prefix="X")
        assert p.apply_system_prompt(None) is None

    def test_protocol_conformance(self):
        p = RuntimeProfile()
        assert isinstance(p, RuntimeProfileProtocol)


class TestResolveProfile:
    def test_resolve_by_model(self):
        assert resolve_profile(model="claude-3-5-sonnet").name == "anthropic"
        assert resolve_profile(model="gpt-4o").name == "openai"
        assert resolve_profile(model="gemini-1.5-pro").name == "gemini"

    def test_resolve_unknown_falls_back_default(self):
        assert resolve_profile(model="unknown-model").name == DEFAULT_PROFILE_NAME

    def test_resolve_by_explicit_name(self):
        assert resolve_profile(name="anthropic").name == "anthropic"

    def test_builtin_family_profiles_preferred_edit_format(self):
        assert resolve_profile(model="claude-3-opus").preferred_edit_format == "string-replace"
        assert resolve_profile(model="gpt-4o").preferred_edit_format == "patch"
        assert resolve_profile(model="gemini-2.0-flash").preferred_edit_format == "whole-file"

    def test_list_profiles_contains_builtins(self):
        names = list_profiles()
        for expected in ("default", "anthropic", "openai", "gemini"):
            assert expected in names


class TestRegistry:
    def test_register_and_resolve(self):
        reg = RuntimeProfileRegistry()
        profile = RuntimeProfile(name="myfam", system_prompt_suffix="X")
        reg.register("myfam", profile)
        assert reg.resolve(name="myfam") is profile

    def test_register_no_override_raises(self):
        reg = RuntimeProfileRegistry()
        reg.register("a", RuntimeProfile(name="a"))
        with pytest.raises(ValueError):
            reg.register("a", RuntimeProfile(name="a"), override=False)

    def test_register_rejects_non_profile(self):
        reg = RuntimeProfileRegistry()
        with pytest.raises(TypeError):
            reg.register("bad", object())

    def test_resolve_unknown_returns_default(self):
        reg = RuntimeProfileRegistry()
        assert reg.resolve(name="nope").name == DEFAULT_PROFILE_NAME

    def test_global_register_profile(self):
        register_profile("global-test", RuntimeProfile(name="global-test", system_prompt_prefix="G"))
        assert resolve_profile(name="global-test").name == "global-test"


class TestBackwardCompatibility:
    def test_default_profile_produces_identical_prompt(self):
        # With the default profile active, apply is a pure no-op.
        prompt = "Backstory\n\nYour Role: X\n\nYour Goal: Y"
        p = resolve_profile(model=None)
        assert p.name == DEFAULT_PROFILE_NAME
        assert p.apply_system_prompt(prompt) == prompt
