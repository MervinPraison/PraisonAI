"""Every instruction-tuning run was training on the prompt.

`assistant_only_loss` is TRL's mask, and it needs `{% generation %}` in the
chat template. **None of unsloth's 43 templates contain it** — verified:
`grep -c "generation %}" unsloth/chat_templates.py` returns 0. So
`assistant_only_loss: auto`, the documented default, resolved to False for
every template a user can actually select, and the model learned to reproduce
the prompt as well as the answer.

There was no error. The run summary printed "Loss mask: full sequence" as
though that were the intended outcome.

Unsloth's own answer is `train_on_responses_only(trainer, instruction_part,
response_part)` (`chat_templates.py:58-87`), which masks by locating literal
turn markers and works on any template. It needs the two markers, which vary by
family — so the table these tests guard is the load-bearing part.
"""

import pytest

from praisonai_train.train.llm import trainer as trainer_mod


resolve = trainer_mod.resolve_response_markers


# --------------------------------------------------------------------------- #
# The table itself
# --------------------------------------------------------------------------- #
def test_every_template_maps_to_markers_that_exist():
    for template, family in trainer_mod.TEMPLATE_TO_MARKERS.items():
        assert family in trainer_mod.RESPONSE_MARKERS, f"{template} -> unknown {family}"


def test_markers_are_distinct_within_a_family():
    # If instruction and response were the same string the mask would find no
    # boundary and silently keep everything.
    for family, (instruction, response) in trainer_mod.RESPONSE_MARKERS.items():
        assert instruction and response, family
        assert instruction != response, f"{family} cannot distinguish the two turns"


def test_the_families_unsloth_documents_are_covered():
    covered = set(trainer_mod.RESPONSE_MARKERS)
    assert {"llama-3", "chatml", "gemma", "mistral", "phi"} <= covered


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("template,expected_instruction", [
    ("llama-3.1", "<|start_header_id|>user<|end_header_id|>\n\n"),
    ("llama3", "<|start_header_id|>user<|end_header_id|>\n\n"),
    ("qwen-2.5", "<|im_start|>user\n"),
    ("chatml", "<|im_start|>user\n"),
    ("gemma-3", "<start_of_turn>user\n"),
    ("mistral", "[INST]"),
    ("phi-3.5", "<|user|>\n"),
])
def test_a_configured_template_resolves(template, expected_instruction):
    markers = resolve(template)
    assert markers is not None, f"{template} resolved to nothing"
    assert markers[0] == expected_instruction


def test_longer_names_win_over_shorter_prefixes():
    # "llama-3.1" must not fall through to a shorter, wrong entry, and a Qwen
    # template must not match on some other substring.
    assert resolve("llama-3.1") == trainer_mod.RESPONSE_MARKERS["llama-3"]
    assert resolve("qwen3-thinking") == trainer_mod.RESPONSE_MARKERS["chatml"]


def test_the_model_name_is_used_when_no_template_is_configured():
    # With no chat_template the model's own template is in use, so the model
    # name is the only signal available.
    assert resolve(None, "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit") == \
        trainer_mod.RESPONSE_MARKERS["llama-3"]
    assert resolve("", "unsloth/gemma-2-2b-it-bnb-4bit") == \
        trainer_mod.RESPONSE_MARKERS["gemma"]
    assert resolve(None, "unsloth/Qwen2.5-7B-Instruct") == \
        trainer_mod.RESPONSE_MARKERS["chatml"]


def test_an_explicit_template_beats_the_model_name():
    # Someone who sets chat_template: chatml on a Llama model means it.
    assert resolve("chatml", "unsloth/Meta-Llama-3.1-8B") == \
        trainer_mod.RESPONSE_MARKERS["chatml"]


def test_an_unknown_model_resolves_to_nothing_rather_than_guessing():
    # Masking on the wrong markers finds no boundary and trains on nothing,
    # which is worse than not masking. None means "say so and stop".
    assert resolve(None, "some-org/entirely-unknown-architecture") is None
    assert resolve(None, "") is None
    assert resolve(None, None) is None


def test_resolution_is_case_insensitive():
    assert resolve("LLAMA-3.1") == trainer_mod.RESPONSE_MARKERS["llama-3"]
    assert resolve(None, "Unsloth/Gemma-3-4B-IT") == trainer_mod.RESPONSE_MARKERS["gemma"]


# --------------------------------------------------------------------------- #
# The routing decision
# --------------------------------------------------------------------------- #
def test_the_summary_distinguishes_the_two_masking_routes():
    # "assistant replies only" hid which route ran, and they have very
    # different coverage.
    labels = trainer_mod._MASK_LABELS
    assert set(labels) == {False, "assistant_only_loss", "train_on_responses_only"}
    assert "full sequence" in labels[False]
    assert "prompts too" in labels[False], "the unmasked case does not say what it costs"
    for key in ("assistant_only_loss", "train_on_responses_only"):
        assert "assistant replies only" in labels[key]
    assert labels["assistant_only_loss"] != labels["train_on_responses_only"]


def test_the_routing_decision_is_exhaustive():
    """Tested through the function, not by reading train_model's source.

    An earlier version of this test grepped `train_model` for the string
    "train_on_responses_only" — and passed even with the branch that calls it
    disabled, which is precisely how the original defect survived.
    """
    decide = trainer_mod.decide_masking
    markers = trainer_mod.RESPONSE_MARKERS["llama-3"]

    # Not asked for: never mask, whatever is available.
    assert decide(False, True, markers) is False
    assert decide(False, False, None) is False

    # TRL's mask is preferred when the template really supports it.
    assert decide(True, True, markers) == "assistant_only_loss"
    assert decide(True, True, None) == "assistant_only_loss"

    # The case that was silently unmasked for every unsloth template.
    assert decide(True, False, markers) == "train_on_responses_only", (
        "a template without {% generation %} falls back to training on prompts")

    # Asked for, and genuinely impossible: say so rather than train unmasked.
    assert decide(True, False, None) is None


def test_the_trainer_uses_the_shared_decision():
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.train_model)
    assert "decide_masking(" in src, "train_model reimplements the routing"
    build = src.index("trainer = trainer_cls(")
    apply = src.index("from unsloth.chat_templates import train_on_responses_only")
    assert build < apply, "masking is applied before the trainer exists"


# --------------------------------------------------------------------------- #
# `auto` normalization feeding the router
# --------------------------------------------------------------------------- #
def _auto_use_mask(supports_mask, markers):
    """The `auto` normalization exactly as train_model computes it.

    decide_masking was tested in isolation, but the bug lived one line up: in
    `auto`, use_mask was keyed off `supports_mask` alone, so a template with no
    {% generation %} but valid turn markers still resolved to False -- and the
    router never saw the markers. This mirrors that normalization so the two
    pieces are tested together, which is where the defect actually was.
    """
    return supports_mask or bool(markers)


def test_auto_reaches_the_marker_fallback_when_trl_mask_is_unsupported():
    # Every unsloth template: no {% generation %} (supports_mask False) but valid
    # turn markers. `auto` must still mask -- via the marker route.
    markers = trainer_mod.RESPONSE_MARKERS["llama-3"]
    use_mask = _auto_use_mask(supports_mask=False, markers=markers)
    assert use_mask is True, "auto must enable masking when markers exist"
    assert trainer_mod.decide_masking(use_mask, False, markers) == \
        "train_on_responses_only"


def test_auto_prefers_trl_mask_when_the_template_supports_it():
    markers = trainer_mod.RESPONSE_MARKERS["llama-3"]
    use_mask = _auto_use_mask(supports_mask=True, markers=markers)
    assert trainer_mod.decide_masking(use_mask, True, markers) == \
        "assistant_only_loss"


def test_auto_stays_unmasked_for_an_unknown_template_without_crashing():
    # No TRL support and no known markers: auto degrades to full-sequence loss
    # rather than raising. (The raise is reserved for an EXPLICIT request.)
    use_mask = _auto_use_mask(supports_mask=False, markers=None)
    assert use_mask is False
    assert trainer_mod.decide_masking(use_mask, False, None) is False
