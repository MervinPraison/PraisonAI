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
