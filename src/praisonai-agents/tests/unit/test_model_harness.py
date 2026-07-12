"""Tests for the model-family-aware harness resolver.

Covers: family A (anthropic) resolves a patch-first harness, family B (openai)
resolves a replace-first harness, and unknown models reproduce the current
generic behaviour byte-for-byte (default profile + unchanged toolset ordering).
"""

import pytest

from praisonaiagents.model_harness import (
    HarnessProfile,
    resolve_harness,
    register_profile,
    DEFAULT_PROFILE,
)
from praisonaiagents.toolsets import ToolsetRegistry


def test_default_profile_is_behaviour_preserving():
    assert DEFAULT_PROFILE.base_prompt is None
    assert DEFAULT_PROFILE.preferred_edit_format is None


def test_unknown_model_falls_back_to_default():
    profile = resolve_harness("some-unknown-model-xyz")
    assert profile is DEFAULT_PROFILE
    assert profile.base_prompt is None
    assert profile.preferred_edit_format is None


def test_none_model_falls_back_to_default():
    assert resolve_harness(None) is DEFAULT_PROFILE
    assert resolve_harness("") is DEFAULT_PROFILE


def test_family_a_anthropic_resolves_patch_first():
    profile = resolve_harness("claude-opus-4")
    assert profile.name == "anthropic"
    assert profile.preferred_edit_format == "apply_patch"
    assert profile.base_prompt


def test_family_b_openai_resolves_replace_first():
    profile = resolve_harness("gpt-4o")
    assert profile.name == "openai"
    assert profile.preferred_edit_format == "edit_file"
    assert profile.base_prompt


def test_matching_is_case_insensitive():
    assert resolve_harness("CLAUDE-3-5-SONNET").name == "anthropic"
    assert resolve_harness("OpenAI/GPT-4").name == "openai"


def test_register_profile_overrides_defaults():
    custom = HarnessProfile(
        name="custom", base_prompt="custom guidance", preferred_edit_format="edit_file"
    )
    register_profile(["claude"], custom)
    try:
        assert resolve_harness("claude-opus-4") is custom
    finally:
        # Clean up: remove the override we prepended.
        from praisonaiagents.model_harness import profiles as _p
        with _p._registry_lock:
            _p._registry[:] = list(_p._DEFAULT_REGISTRY)


def test_coding_toolset_unknown_model_is_byte_for_byte():
    reg = ToolsetRegistry()
    baseline = reg.resolve_toolset("coding")
    # No model → identical ordering.
    assert reg.resolve_toolset_for_model("coding", None) == baseline
    # Unknown model → identical ordering (default profile).
    assert reg.resolve_toolset_for_model("coding", "unknown-model") == baseline


def test_coding_toolset_anthropic_prefers_apply_patch_first():
    reg = ToolsetRegistry()
    tools = reg.resolve_toolset_for_model("coding", "claude-opus-4")
    ep = [t for t in tools if t in ("edit_file", "apply_patch")]
    assert ep[0] == "apply_patch"
    # Both primitives remain available.
    assert set(ep) == {"edit_file", "apply_patch"}
    # Same set of tools as baseline, just reordered.
    assert set(tools) == set(reg.resolve_toolset("coding"))


def test_coding_toolset_openai_prefers_edit_file_first():
    reg = ToolsetRegistry()
    tools = reg.resolve_toolset_for_model("coding", "gpt-4o")
    ep = [t for t in tools if t in ("edit_file", "apply_patch")]
    assert ep[0] == "edit_file"
    assert set(ep) == {"edit_file", "apply_patch"}
    assert set(tools) == set(reg.resolve_toolset("coding"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
