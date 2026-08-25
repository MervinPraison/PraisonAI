"""GRPO and the trainers behind it — the last of unsloth's methods.

Unsloth rewrites every `trl.trainer.*_trainer` module generically
(`rl.py:4235-4248`), so GRPO, reward modelling and CPO all work through it.
praisonai-train had none of them, and GRPO was the blocker for the rest: it
needs reward functions, and a YAML config can only carry a string.

**The convention chosen is a dotted import path**, `module:function`, the same
form `console_scripts` and gunicorn use. A registry populated by decorator
would mean the config can only name functions from a module something else
already imported; inline Python in YAML is a code-execution surface in a file
people paste from the internet. An import path is the only one of the three
that can be checked before anything runs.
"""

import pytest

from praisonai_train import rewards
from praisonai_train.train.llm import trainer as trainer_mod


def good_reward(prompts, completions, **kwargs):
    """A well-shaped reward function, used as a fixture by import path."""
    return [float(len(c)) for c in completions]


def wrong_shape(x):
    return []


not_a_function = 42


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_a_dotted_path_resolves_to_the_callable():
    fn = rewards.resolve(f"{__name__}:good_reward")
    assert fn is good_reward


def test_an_already_callable_spec_passes_through():
    assert rewards.resolve(good_reward) is good_reward


def test_a_missing_module_and_a_missing_attribute_are_told_apart():
    # They need different fixes: one is PYTHONPATH, the other is a typo in the
    # function name. The bare ImportError does not say which happened.
    with pytest.raises(rewards.RewardError) as no_module:
        rewards.resolve("definitely_not_a_module:f")
    assert "cannot import" in str(no_module.value)

    with pytest.raises(rewards.RewardError) as no_attr:
        rewards.resolve(f"{__name__}:no_such_function")
    assert "has no 'no_such_function'" in str(no_attr.value)


def test_a_missing_attribute_lists_what_is_there():
    with pytest.raises(rewards.RewardError) as e:
        rewards.resolve(f"{__name__}:no_such_function")
    assert "good_reward" in str(e.value), "the error does not say what is available"


def test_a_malformed_spec_says_what_the_form_is():
    with pytest.raises(rewards.RewardError) as e:
        rewards.resolve("myproject.rewards.length_penalty")   # dot, not colon
    assert "module:function" in str(e.value)


def test_a_non_callable_is_refused_by_type():
    with pytest.raises(rewards.RewardError) as e:
        rewards.resolve(f"{__name__}:not_a_function")
    assert "int" in str(e.value)


def test_every_broken_path_is_reported_at_once():
    # Three broken paths should be three fixes in one pass, not three runs.
    with pytest.raises(rewards.RewardError) as e:
        rewards.resolve_all(["nomodule_a:f", "nomodule_b:g", f"{__name__}:nope"])
    text = str(e.value)
    assert text.count("\n") >= 2, f"only reported one of three:\n{text}"


def test_a_single_spec_does_not_have_to_be_a_list():
    assert rewards.resolve_all(f"{__name__}:good_reward") == [good_reward]


def test_no_rewards_is_an_empty_list_not_an_error():
    assert rewards.resolve_all(None) == []


# --------------------------------------------------------------------------- #
# Shape check
# --------------------------------------------------------------------------- #
def test_a_well_shaped_function_passes_quietly():
    assert rewards.check_signature(good_reward) is None


def test_a_wrong_shaped_function_is_flagged_with_the_expected_call():
    note = rewards.check_signature(wrong_shape, "m:wrong_shape")
    assert note and "completions" in note
    assert "(prompts, completions, **kwargs)" in note


def test_a_callable_with_no_readable_signature_is_left_to_trl(monkeypatch):
    """Guessing about a callable we cannot inspect would refuse working code.

    The first version of this test used `len` on the assumption that
    inspect.signature raises for builtins. It does not in modern Python — and
    flagging `len` is the right answer, since it genuinely is not a reward
    function. So the except branch is exercised directly.
    """
    import inspect as _inspect

    def _raises(*a, **k):
        raise ValueError("no signature for this")

    monkeypatch.setattr(rewards.inspect, "signature", _raises)
    assert rewards.check_signature(good_reward) is None


def test_something_that_is_plainly_not_a_reward_function_is_flagged():
    note = rewards.check_signature(len, "builtins:len")
    assert note and "completions" in note


# --------------------------------------------------------------------------- #
# The methods
# --------------------------------------------------------------------------- #
def test_grpo_reward_and_cpo_are_offered():
    assert {"grpo", "reward", "cpo"} <= set(trainer_mod.TRAINING_METHODS)


def test_grpo_takes_prompts_only():
    # It generates its own completions, so a completions column is not needed
    # and requiring one would reject a correct corpus.
    assert trainer_mod.TRAINING_METHODS["grpo"]["columns"] == ("prompt",)


def test_grpo_is_the_only_method_needing_rewards():
    needs = {k for k, v in trainer_mod.TRAINING_METHODS.items()
             if v.get("needs_rewards")}
    assert needs == {"grpo"}


def test_reward_modelling_takes_preference_pairs():
    assert set(trainer_mod.TRAINING_METHODS["reward"]["columns"]) == {"chosen", "rejected"}


def test_cpo_needs_no_reference_model():
    # Like ORPO, it folds the reference into its loss.
    assert trainer_mod.TRAINING_METHODS["cpo"]["needs_ref_model"] is False


def test_rewards_are_resolved_before_the_model_loads():
    """A typo should cost five seconds, not a multi-gigabyte load."""
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.train_model)
    resolve = src.index("resolve_all(")
    build = src.index("trainer = trainer_cls(")
    assert resolve < build


def test_grpo_without_reward_funcs_is_refused():
    """Tested by calling the guard, not by grepping train_model.

    A source-text assertion passes with the branch disabled — the message is
    still in the file. That is how a guard like this quietly stops guarding.
    """
    with pytest.raises(rewards.RewardError) as e:
        rewards.require("grpo", [])
    text = str(e.value)
    assert "module:function" in text
    assert "reward_funcs:" in text, "the error does not show the config shape"


def test_a_method_with_rewards_passes_the_guard():
    assert rewards.require("grpo", [good_reward]) == [good_reward]


def test_the_trainer_routes_through_the_shared_guard():
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.train_model)
    assert "require(method," in src, "train_model reimplements the check"
