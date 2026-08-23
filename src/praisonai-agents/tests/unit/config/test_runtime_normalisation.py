"""runtime= must normalise spelling and reject typos, not degrade silently.

Regression for #4229: an unrecognised runtime name was stored verbatim and
silently dropped nine of twelve capabilities. Spelling variants of a known
runtime must all resolve to the same canonical name; a close typo must raise;
a genuinely unknown plugin runtime name must still be accepted (it falls back
to the reduced harness through the runtime registry, not a closed literal).
"""
import pytest

from praisonaiagents.config.feature_configs import (
    RuntimeConfig,
    canonical_runtime_name,
    resolve_runtime,
)


NATIVE_SPELLINGS = ["native", "NATIVE", " native ", "Native", "nAtIvE"]


@pytest.mark.parametrize("spelling", NATIVE_SPELLINGS)
def test_native_spelling_variants_canonicalise(spelling):
    assert canonical_runtime_name(spelling) == "native"
    assert resolve_runtime(spelling).preferred_runtime == "native"


@pytest.mark.parametrize(
    "spelling", ["plugin-harness", "plugin_harness", "harness", "plugin", "reduced"]
)
def test_harness_aliases_canonicalise(spelling):
    assert canonical_runtime_name(spelling) == "plugin-harness"
    assert resolve_runtime(spelling).preferred_runtime == "plugin-harness"


@pytest.mark.parametrize("typo", ["nativ", "natve", "reducd", "harnes"])
def test_close_typo_raises_with_suggestion(typo):
    with pytest.raises(ValueError):
        canonical_runtime_name(typo)


def test_unknown_plugin_runtime_is_accepted_verbatim():
    """A genuinely unknown name is an opaque plugin runtime, not a typo."""
    assert canonical_runtime_name("my-plugin-runtime") == "my-plugin-runtime"
    cfg = resolve_runtime("my-plugin-runtime")
    assert cfg.preferred_runtime == "my-plugin-runtime"


def test_runtime_config_input_is_normalised():
    cfg = resolve_runtime(RuntimeConfig(preferred_runtime="NATIVE"))
    assert cfg.preferred_runtime == "native"


def test_dict_input_is_normalised():
    cfg = resolve_runtime({"preferred_runtime": " native "})
    assert cfg.preferred_runtime == "native"


def test_runtime_config_input_is_not_mutated():
    """resolve_runtime returns a normalised copy; the caller's object stands."""
    original = RuntimeConfig(preferred_runtime="NATIVE")
    resolved = resolve_runtime(original)
    assert original.preferred_runtime == "NATIVE"
    assert resolved is not original
    assert resolved.preferred_runtime == "native"


def test_close_typo_error_suggests_matched_alias():
    with pytest.raises(ValueError) as exc:
        canonical_runtime_name("reducd")
    assert "reduced" in str(exc.value)


def test_agent_normalises_runtime_spelling():
    """Smoke: Agent construction canonicalises a spelling variant."""
    from praisonaiagents import Agent

    agent = Agent(instructions="test", runtime="NATIVE")
    assert agent._runtime_config.preferred_runtime == "native"


def test_agent_rejects_runtime_config_typo():
    """A typo in a direct RuntimeConfig must raise, not degrade silently."""
    from praisonaiagents import Agent

    with pytest.raises(ValueError):
        Agent(instructions="test", runtime=RuntimeConfig(preferred_runtime="nativ"))
