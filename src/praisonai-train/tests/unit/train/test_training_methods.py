"""Preference tuning was unreachable.

Unsloth patches TRL's DPO, ORPO and KTO trainers alongside SFT -- they are named
in the list of trainers it rewrites at `unsloth/__init__.py:1438-1443`. This
module could only ever construct an `SFTTrainer`, so a dataset of
chosen/rejected pairs had nowhere to go: half of what the backing library
supports could not be reached from PraisonAI at all.

The tests below cover the config surface rather than a real run, because a real
run needs a GPU. What they do assert is everything that decides *which* trainer
is built and *whether it can be*, which is where a silent mismatch would cost
someone a full GPU session.
"""

import pytest

from praisonai_train.train.llm import trainer as trainer_mod


def _cfg(**over):
    base = {
        "model_name": "unsloth/gemma-2-2b-it-bnb-4bit",
        "max_seq_length": 2048,
        "dataset": "some/dataset",
    }
    base.update(over)
    obj = trainer_mod.TrainModel.__new__(trainer_mod.TrainModel)
    obj.config = base
    return obj


class _Cols:
    """Minimal stand-in for a datasets.Dataset: only column_names is read."""

    def __init__(self, names):
        self.column_names = list(names)


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
def test_the_methods_unsloth_patches_are_all_offered():
    # If unsloth grows one and this does not, the gap reopens silently.
    assert set(trainer_mod.TRAINING_METHODS) == {"sft", "dpo", "orpo", "kto"}


def test_every_method_declares_what_it_needs():
    for name, spec in trainer_mod.TRAINING_METHODS.items():
        assert spec["trainer"].endswith("Trainer"), name
        assert spec["config"].endswith("Config"), name
        assert isinstance(spec["columns"], tuple), name
        assert isinstance(spec["needs_ref_model"], bool), name
        # A phrase that completes "method X: ...", not a sentence. No case
        # rule: "Kahneman-Tversky" is a proper noun and rightly capitalised.
        assert spec["summary"], name
        assert not spec["summary"].endswith("."), name


def test_orpo_needs_no_reference_model():
    # ORPO folds the reference into its loss. Holding a second frozen model
    # would double VRAM for nothing.
    assert trainer_mod.TRAINING_METHODS["orpo"]["needs_ref_model"] is False
    assert trainer_mod.TRAINING_METHODS["dpo"]["needs_ref_model"] is True


def test_sft_stays_the_default():
    cfg = {}
    assert trainer_mod.TrainModel.resolve_method(cfg) == "sft"
    assert cfg["method"] == "sft"


# --------------------------------------------------------------------------- #
# Validation, before the GPU time is spent
# --------------------------------------------------------------------------- #
def test_an_unknown_method_is_refused_by_name():
    with pytest.raises(ValueError) as e:
        trainer_mod.TrainModel.resolve_method({"method": "ppo"})
    msg = str(e.value)
    assert "ppo" in msg
    for offered in ("sft", "dpo", "orpo", "kto"):
        assert offered in msg, f"the error does not say {offered} is available"


def test_the_method_is_case_insensitive():
    cfg = {"method": "DPO"}
    assert trainer_mod.TrainModel.resolve_method(cfg) == "dpo"
    assert cfg["method"] == "dpo", "the normalised value is not written back"


def test_validate_config_routes_through_the_same_check():
    # Otherwise the two could disagree about what a valid method is.
    import inspect
    src = inspect.getsource(trainer_mod.TrainModel.validate_config)
    assert "resolve_method" in src


@pytest.mark.parametrize(
    "method,columns",
    [("dpo", ("prompt", "chosen", "rejected")),
     ("orpo", ("prompt", "chosen", "rejected")),
     ("kto", ("prompt", "completion", "label"))],
)
def test_a_correctly_shaped_dataset_passes(method, columns):
    trainer_mod.TrainModel._require_columns(_Cols(columns), columns, method)


def test_a_wrongly_shaped_dataset_names_the_missing_columns():
    # TRL's own failure for this surfaces inside the collator, minutes in and
    # phrased in terms of tensors rather than the file the user pointed at.
    with pytest.raises(ValueError) as e:
        trainer_mod.TrainModel._require_columns(
            _Cols(["text"]), ("prompt", "chosen", "rejected"), "dpo")
    msg = str(e.value)
    assert "chosen" in msg and "rejected" in msg
    assert "text" in msg, "the error does not say what the dataset actually has"


def test_an_sft_dataset_used_for_dpo_is_caught():
    # The realistic mistake: an existing SFT corpus pointed at method: dpo.
    with pytest.raises(ValueError):
        trainer_mod.TrainModel._require_columns(
            _Cols(["instruction", "output", "text"]),
            trainer_mod.TRAINING_METHODS["dpo"]["columns"], "dpo")


def test_sft_requires_no_particular_columns():
    trainer_mod.TrainModel._require_columns(_Cols(["anything"]), (), "sft")


def test_an_empty_dataset_still_reports_usefully():
    with pytest.raises(ValueError) as e:
        trainer_mod.TrainModel._require_columns(_Cols([]), ("prompt",), "dpo")
    assert "none" in str(e.value)


# --------------------------------------------------------------------------- #
# The config keys the new methods need must be accepted
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key", ["method", "beta", "max_prompt_length", "desirable_weight", "undesirable_weight"])
def test_preference_keys_are_not_reported_as_unknown(key):
    # The validator warns on unrecognised keys; a key the feature needs must not
    # be one of them, or every DPO config prints a spurious warning.
    assert key in trainer_mod.TrainModel.KNOWN_KEYS, f"{key} would warn as unknown"


# --------------------------------------------------------------------------- #
# The dataset must survive long enough for the trainer to read it
# --------------------------------------------------------------------------- #
def test_a_preference_dataset_is_not_flattened_to_text():
    """The defect that made the whole feature unreachable.

    `process_dataset` ends with
    `dataset.map(format_func, remove_columns=dataset.column_names)`, which
    collapses every row to a single `text` column for SFT. Applied to a
    preference dataset that destroys prompt/chosen/rejected *before* the trainer
    reads them, so every DPO run died with "the dataset has ['text']" — the
    method could never have worked on a real corpus.
    """
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.process_dataset)
    flatten = src.index("remove_columns=dataset.column_names")
    guard = src.index('self.config.get("method", "sft") != "sft"')
    assert guard < flatten, (
        "process_dataset flattens the dataset before checking the method; "
        "a preference dataset loses its columns")
    # And the guard must return, not merely warn.
    between = src[guard:flatten]
    assert "return dataset" in between, "the method guard does not short-circuit"


def test_sft_still_gets_its_text_column():
    # The guard must not change the SFT path, which needs the flattening.
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.process_dataset)
    assert "remove_columns=dataset.column_names" in src
    assert "formatting_prompts_func" in src
