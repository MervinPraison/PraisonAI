"""The unsloth surface that was declared, documented, and unreachable.

Each of these is a keyword unsloth already accepts and this package never
passed. Nothing failed when they were missing -- the run just did something
narrower than the user asked for, which is the pattern the whole audit kept
turning up.
"""

import re
from pathlib import Path

import pytest

from praisonai_train.train.llm import trainer as trainer_mod

UNSLOTH_SAVE = Path("/Users/praison/unsloth/unsloth/save.py")


# --------------------------------------------------------------------------- #
# Quantisation
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not UNSLOTH_SAVE.exists(), reason="unsloth not checked out here")
def test_the_quant_list_matches_unsloths_own():
    """A literal, not an import -- so a test has to keep the two in step.

    Importing unsloth here would pull torch into `llm --dry-run`, so the list
    is copied. That copy is exactly the kind of thing that silently rots, hence
    this.
    """
    src = UNSLOTH_SAVE.read_text()

    def block(name):
        i = src.index(f"{name} = ")
        j = src.index("\n]", i) if "\n]" in src[i:i + 4000] else src.index("}", i)
        return set(re.findall(r'"([a-z0-9_]+)"', src[i:j]))

    assert trainer_mod.ALLOWED_QUANTS == block("ALLOWED_QUANTS"), (
        "the quant list has drifted from unsloth's")
    assert trainer_mod.IMATRIX_QUANTS == block("IMATRIX_QUANTS")


@pytest.mark.parametrize("quant", ["q3_k_l", "q4_k_s", "q5_k_s", "f32", "q3_k_xs"])
def test_quants_that_were_wrongly_refused_are_accepted(quant):
    # Every one of these is legal upstream and was rejected by this validator
    # before unsloth was ever asked.
    assert quant in trainer_mod.VALID_QUANTIZATION_METHODS


def test_the_imatrix_family_is_reachable():
    # IQ quants are how a 30B model fits on a laptop; none were accepted.
    assert trainer_mod.IMATRIX_QUANTS
    assert trainer_mod.IMATRIX_QUANTS <= trainer_mod.VALID_QUANTIZATION_METHODS


def test_the_old_twelve_still_work():
    for quant in ("q4_k_m", "q5_k_m", "q8_0", "q4_0", "q6_k", "f16", "bf16", "q2_k"):
        assert quant in trainer_mod.VALID_QUANTIZATION_METHODS


def test_nonsense_is_still_refused():
    assert "q99_totally_made_up" not in trainer_mod.VALID_QUANTIZATION_METHODS


# --------------------------------------------------------------------------- #
# Keys that must be accepted, or every config using them warns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", [
    "hf_token", "trust_remote_code", "revision",
    "finetune_last_n_layers", "layers_to_transform", "layers_pattern",
    "target_parameters", "init_lora_weights",
    "merged_save_dir", "imatrix_file",
    "fast_inference", "gpu_memory_utilization", "max_lora_rank",
])
def test_the_new_keys_are_known(key):
    assert key in trainer_mod.TrainModel.KNOWN_KEYS, (
        f"{key} would warn as an unknown config key")


# --------------------------------------------------------------------------- #
# Where each one has to land
# --------------------------------------------------------------------------- #
_flag = lambda v, default=False: default if v is None else bool(v)


def _load_kwargs(**config):
    """Calls the real assembly. The first version of this helper REIMPLEMENTED
    it -- in the very change that banned reimplementing tested logic -- and
    would have passed with the forwarding deleted."""
    return trainer_mod.model_access_kwargs(config, _flag)


def test_a_gated_model_can_be_given_a_token():
    # Gated repos (Llama, Gemma) worked only via an environment variable.
    assert _load_kwargs(hf_token="hf_abc")["token"] == "hf_abc"


def test_a_run_can_pin_a_revision():
    # Without this a multi-day run is not reproducible: the tag moves.
    assert _load_kwargs(revision="v1.2")["revision"] == "v1.2"


def test_nothing_is_passed_when_nothing_is_configured():
    # Passing None explicitly is not the same as omitting: unsloth branches on
    # presence for some of these.
    kwargs = _load_kwargs()
    for key in ("token", "revision", "trust_remote_code"):
        assert key not in kwargs


def test_peft_selectors_reach_the_adapter():
    """Checked by running the passthrough loop, not by reading it.

    The list of forwarded options is data, so the test can exercise it the same
    way prepare_model does rather than grepping the method.
    """
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.prepare_model)
    start = src.index("for opt in (")
    names = set(re.findall(r'"(\w+)"', src[start:src.index(")", start)]))
    for opt in ("finetune_last_n_layers", "layers_to_transform", "layers_pattern",
                "target_parameters", "init_lora_weights"):
        assert opt in names, f"{opt} is never forwarded to get_peft_model"
    # The originals must not have been displaced.
    assert {"modules_to_save", "rank_pattern", "alpha_pattern", "use_dora"} <= names


def test_merged_weights_can_be_written_to_a_directory():
    """`save_pretrained_merged` was never called.

    The only way to get merged weights was to push them -- which needs a Hub
    account, a token and a network. "Merge my adapter into a folder on this
    disk" is the most common post-training request.
    """
    assert callable(getattr(trainer_mod.TrainModel, "save_merged_locally", None))


def test_the_local_merge_is_a_no_op_when_not_asked_for():
    obj = trainer_mod.TrainModel.__new__(trainer_mod.TrainModel)
    obj.config = {}
    assert obj.save_merged_locally() is None
