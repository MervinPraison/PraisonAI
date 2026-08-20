"""Preset-name typos must raise, not silently fall back to defaults.

Regression test: Agent(output="streem") used to construct successfully with
verbose=False (the silent default) instead of reporting the typo.
"""
import pytest

from praisonaiagents import Agent

# (param, typo, expected suggestion in the error message)
TYPOED_PRESETS = [
    ("output", "streem", "stream"),
    ("execution", "balancd", "balanced"),
    ("context", "sliding_windo", "sliding_window"),
    ("autonomy", "full_atuo", "full_auto"),
    ("approval", "read_onl", "read_only"),
    ("learn", "agentik", "agentic"),
    ("self_improve", "backgrond", "background"),
    # Already-validated params — kept here so the guarantee is uniform.
    ("memory", "postgress", "postgres"),
    ("reflection", "thorogh", "thorough"),
]


@pytest.mark.parametrize("param,typo,suggestion", TYPOED_PRESETS)
def test_typoed_preset_raises_with_suggestion(param, typo, suggestion):
    with pytest.raises(ValueError) as exc:
        Agent(instructions="t", **{param: typo})
    msg = str(exc.value)
    assert typo in msg
    assert suggestion in msg


VALID_PRESETS = [
    ("output", "verbose"),
    ("output", "silent"),
    ("output", "VERBOSE"),  # case-insensitive lookup
    ("execution", "fast"),
    ("execution", "THOROUGH"),
    ("context", "summarize"),
    ("autonomy", "full_auto"),
    ("approval", "read_only"),
    ("approval", "plan"),
    ("learn", "disabled"),
    ("self_improve", "background"),
]


@pytest.mark.parametrize("param,value", VALID_PRESETS)
def test_valid_preset_still_accepted(param, value):
    assert Agent(instructions="t", **{param: value}) is not None


def test_output_still_accepts_a_file_path():
    """output= doubles as an output-file path; that escape hatch must survive."""
    agent = Agent(instructions="t", output="report.md")
    assert agent._output_file == "report.md"


@pytest.mark.parametrize("value", [True, False, {"verbose": True}, None])
def test_non_string_output_untouched(value):
    assert Agent(instructions="t", output=value) is not None


def test_freeform_string_params_are_not_validated():
    """These take arbitrary identifiers, not presets — they must NOT raise."""
    assert Agent(instructions="t", knowledge="notes.pdf") is not None
    assert Agent(instructions="t", guardrails="Answer must cite a source.") is not None
    assert Agent(instructions="t", runtime="my-plugin-runtime") is not None


# ---------------------------------------------------------------------------
# Regression: validation must accept every spelling the downstream resolver
# accepts, otherwise it turns previously-valid construction into a hard error
# (approval hyphen aliases) or accepts a value the resolver then silently drops
# (learn / context / autonomy case + whitespace).
# ---------------------------------------------------------------------------

# approval= routes through PermissionMode.resolve, which treats -/_ as
# interchangeable. These aliases were valid before this PR and must stay valid.
HYPHENATED_APPROVAL_ALIASES = [
    "accept-edits",
    "bypass-permissions",
    "full-auto",
    "dont-ask",
    "no-ask",
    "auto-edit",
]


@pytest.mark.parametrize("value", HYPHENATED_APPROVAL_ALIASES)
def test_hyphenated_approval_aliases_accepted(value):
    """Hyphen spellings resolve onto the same PermissionMode as underscores."""
    agent = Agent(instructions="t", approval=value)
    assert agent is not None
    assert agent._permission_mode is not None


# Case/whitespace variants of valid presets must construct AND resolve to the
# intended feature, never silently fall back to the disabled default.
NORMALIZED_VALID_PRESETS = [
    ("context", " summarize "),
    ("context", "SUMMARIZE"),
    ("autonomy", " full_auto "),
    ("autonomy", "FULL_AUTO"),
    ("learn", " agentic "),
    ("learn", "AGENTIC"),
]


@pytest.mark.parametrize("param,value", NORMALIZED_VALID_PRESETS)
def test_normalized_preset_accepted(param, value):
    assert Agent(instructions="t", **{param: value}) is not None


@pytest.mark.parametrize("value", [" agentic ", "AGENTIC", "propose", " PROPOSE "])
def test_learn_case_whitespace_not_silently_disabled(value):
    """learn= with a valid-but-unnormalized string must still enable learning."""
    agent = Agent(instructions="t", learn=value)
    assert agent._learn_config is not None


# Security: the deny-set preset lookup must be hyphen-tolerant too, so
# approval="read-only" applies the full deny set instead of an empty one.
@pytest.mark.parametrize("value", ["read_only", "read-only", "READ_ONLY", " read-only "])
def test_read_only_hyphen_variants_apply_full_deny_set(value):
    agent = Agent(instructions="t", approval=value)
    assert len(agent._perm_deny) > 0
