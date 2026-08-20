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
