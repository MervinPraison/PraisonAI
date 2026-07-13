"""Tests for opt-in prompt profiles."""

import pytest

from praisonaiagents.runtime.prompt_profiles import (
    PromptProfile,
    PromptProfileProtocol,
    PromptProfileRegistry,
    resolve_profile,
    register_profile,
    list_profiles,
    DEFAULT_PROFILE_NAME,
)


@pytest.fixture(autouse=True)
def _reset_global_registry():
    """Reset the global profile registry before and after each test.

    Prevents profiles registered by one test (e.g. ``global-test``) from
    leaking into later tests and causing order-dependent results.
    """
    from praisonaiagents.runtime.prompt_profiles import _global_registry
    _global_registry.clear()
    yield
    _global_registry.clear()


class TestPromptProfile:
    def test_default_is_prompt_neutral(self):
        p = PromptProfile()
        assert p.is_prompt_neutral is True
        assert p.name == DEFAULT_PROFILE_NAME

    def test_default_apply_is_noop(self):
        p = PromptProfile()
        prompt = "You are a helpful assistant."
        assert p.apply_system_prompt(prompt) == prompt

    def test_prefix_and_suffix_applied(self):
        p = PromptProfile(
            name="custom",
            system_prompt_prefix="PREFIX",
            system_prompt_suffix="SUFFIX",
        )
        assert p.is_prompt_neutral is False
        result = p.apply_system_prompt("BODY")
        assert result == "PREFIX\n\nBODY\n\nSUFFIX"

    def test_prefix_only(self):
        p = PromptProfile(system_prompt_prefix="PREFIX")
        assert p.apply_system_prompt("BODY") == "PREFIX\n\nBODY"

    def test_suffix_only(self):
        p = PromptProfile(system_prompt_suffix="SUFFIX")
        assert p.apply_system_prompt("BODY") == "BODY\n\nSUFFIX"

    def test_apply_handles_none(self):
        p = PromptProfile(system_prompt_prefix="X")
        assert p.apply_system_prompt(None) is None

    def test_protocol_conformance(self):
        p = PromptProfile()
        assert isinstance(p, PromptProfileProtocol)

    def test_from_dict_valid(self):
        p = PromptProfile.from_dict({"name": "x", "system_prompt_prefix": "P"})
        assert p.name == "x"
        assert p.system_prompt_prefix == "P"

    def test_from_dict_rejects_unknown_key(self):
        with pytest.raises(ValueError):
            PromptProfile.from_dict({"systemPromptPrefix": "typo"})

    def test_from_dict_rejects_non_mapping(self):
        with pytest.raises(TypeError):
            PromptProfile.from_dict("not-a-dict")


class TestResolveProfile:
    def test_resolve_unknown_falls_back_default(self):
        assert resolve_profile(name="unknown").name == DEFAULT_PROFILE_NAME

    def test_resolve_none_returns_default(self):
        assert resolve_profile().name == DEFAULT_PROFILE_NAME

    def test_resolve_by_explicit_name(self):
        register_profile("myfam", PromptProfile(name="myfam", system_prompt_prefix="P"))
        assert resolve_profile(name="myfam").name == "myfam"

    def test_list_profiles_contains_default(self):
        assert DEFAULT_PROFILE_NAME in list_profiles()


class TestRegistry:
    def test_register_and_resolve(self):
        reg = PromptProfileRegistry()
        profile = PromptProfile(name="myfam", system_prompt_suffix="X")
        reg.register("myfam", profile)
        assert reg.resolve(name="myfam") is profile

    def test_register_no_override_raises(self):
        reg = PromptProfileRegistry()
        reg.register("a", PromptProfile(name="a"))
        with pytest.raises(ValueError):
            reg.register("a", PromptProfile(name="a"), override=False)

    def test_register_rejects_non_profile(self):
        reg = PromptProfileRegistry()
        with pytest.raises(TypeError):
            reg.register("bad", object())

    def test_resolve_unknown_returns_default(self):
        reg = PromptProfileRegistry()
        assert reg.resolve(name="nope").name == DEFAULT_PROFILE_NAME

    def test_global_register_profile(self):
        # Cleanup handled by the autouse _reset_global_registry fixture.
        register_profile("global-test", PromptProfile(name="global-test", system_prompt_prefix="G"))
        assert resolve_profile(name="global-test").name == "global-test"

    def test_default_cannot_be_overridden_with_prompt(self):
        reg = PromptProfileRegistry()
        with pytest.raises(ValueError):
            reg.register(
                DEFAULT_PROFILE_NAME,
                PromptProfile(name=DEFAULT_PROFILE_NAME, system_prompt_prefix="INJECTED"),
            )

    def test_default_neutral_reregister_allowed(self):
        reg = PromptProfileRegistry()
        reg.register(DEFAULT_PROFILE_NAME, PromptProfile(name=DEFAULT_PROFILE_NAME))
        assert reg.resolve(name=DEFAULT_PROFILE_NAME).is_prompt_neutral is True

    def test_global_default_cannot_be_overridden_with_prompt(self):
        with pytest.raises(ValueError):
            register_profile(
                DEFAULT_PROFILE_NAME,
                PromptProfile(name=DEFAULT_PROFILE_NAME, system_prompt_suffix="X"),
            )

    def test_resolve_require_raises_on_unknown_name(self):
        reg = PromptProfileRegistry()
        with pytest.raises(KeyError):
            reg.resolve(name="does-not-exist", require=True)

    def test_resolve_require_returns_registered(self):
        reg = PromptProfileRegistry()
        reg.register("known", PromptProfile(name="known"))
        assert reg.resolve(name="known", require=True).name == "known"

    def test_global_resolve_require_raises(self):
        with pytest.raises(KeyError):
            resolve_profile(name="totally-unknown", require=True)

    def test_clear_resets_to_default_only(self):
        reg = PromptProfileRegistry()
        reg.register("extra", PromptProfile(name="extra", system_prompt_prefix="P"))
        reg.clear()
        assert reg.list_profiles() == [DEFAULT_PROFILE_NAME]


class TestBackwardCompatibility:
    def test_default_profile_produces_identical_prompt(self):
        # With the default profile active, apply is a pure no-op.
        prompt = "Backstory\n\nYour Role: X\n\nYour Goal: Y"
        p = resolve_profile()
        assert p.name == DEFAULT_PROFILE_NAME
        assert p.apply_system_prompt(prompt) == prompt
