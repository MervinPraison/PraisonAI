"""The vision trainer must read its config, and must not publish by default.

train_vision.py is selected automatically for any model whose name contains
vision/-vl-/visionmodel, so a user never chooses this file -- the model name
does. Two defects lived in it.

1. The LoRA adapter was built from literals:

       r=16, lora_alpha=16, lora_dropout=0, random_state=3407, use_rslora=False

   so lora_r / lora_alpha / lora_dropout / random_state / use_rslora were
   accepted in the config, validated, and ignored. A vision run trained at
   r=16 whatever was asked for.

2. Every stage was gated on `self.config.get(<key>, "true").lower() == "true"`
   -- the default being the *string* "true", i.e. publishing ON when the key
   is absent. `praisonai-train llm` writes only the keys the user supplied, so
   `huggingface_save` is usually absent: a plain local run pushed the model to
   the Hub, or died on a missing `hf_model_name` after training had completed.

The LLM trainer already does the right thing, with a comment saying so
("Publishing defaults OFF and is skipped unless a target is set"). This brings
the vision path in line.
"""
import importlib.util
import os
import sys
import types

import pytest


@pytest.fixture(scope="module")
def mod():
    """Load train_vision with its GPU-only dependencies stubbed."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(
        os.path.join(here, "..", "..", "..", "praisonai_train", "train_vision.py"))
    for name in ("torch", "unsloth", "transformers", "datasets", "trl", "peft"):
        module = types.ModuleType(name)
        module.__version__ = "0.0-stub"
        sys.modules.setdefault(name, module)
    spec = importlib.util.spec_from_file_location("train_vision_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cls(mod):
    return mod.TrainVisionModel


def _run(cls, config):
    """Run the stage dispatcher, recording which stages fire."""
    calls = []
    inst = cls.__new__(cls)
    inst.config = config
    for name in ("check_gpu", "check_ram", "print_system_info", "prepare_model",
                 "train_model", "save_model_merged", "push_model_gguf",
                 "create_and_push_ollama_model"):
        setattr(inst, name, (lambda k: (lambda *a, **kw: calls.append(k)))(name))
    cls.run(inst)
    return calls


BASE = {"model_name": "some-vision-model", "train": "false"}


class TestPublishingDefaultsOff:

    def test_a_plain_config_does_not_push_to_the_hub(self, cls):
        assert "save_model_merged" not in _run(cls, dict(BASE))

    def test_a_plain_config_does_not_push_gguf(self, cls):
        assert "push_model_gguf" not in _run(cls, dict(BASE))

    def test_a_plain_config_does_not_push_to_ollama(self, cls):
        assert "create_and_push_ollama_model" not in _run(cls, dict(BASE))

    def test_asking_to_save_without_a_repo_name_skips_rather_than_crashes(self, cls):
        """It used to reach save_model_merged and die on KeyError: 'hf_model_name'."""
        calls = _run(cls, {**BASE, "huggingface_save": True})
        assert "save_model_merged" not in calls

    def test_an_explicit_save_with_a_repo_name_still_publishes(self, cls):
        calls = _run(cls, {**BASE, "huggingface_save": "true", "hf_model_name": "me/m"})
        assert "save_model_merged" in calls

    def test_ollama_needs_its_target_too(self, cls):
        calls = _run(cls, {**BASE, "ollama_save": True, "ollama_model": "m"})
        assert "create_and_push_ollama_model" in calls


class TestFlagsAcceptBothYamlForms:

    def test_a_real_boolean_does_not_crash(self, cls):
        """`train: true` used to hit .lower() on a bool."""
        calls = _run(cls, {"model_name": "v", "train": True})
        assert "train_model" in calls

    def test_a_string_still_works(self, cls):
        calls = _run(cls, {"model_name": "v", "train": "true"})
        assert "train_model" in calls

    def test_training_still_defaults_on(self, cls):
        assert "train_model" in _run(cls, {"model_name": "v"})


def _peft_kwargs(mod, config):
    """Run prepare_model with the model loader stubbed, return the kwargs that
    reached FastVisionModel.get_peft_model -- the arguments that actually train."""
    captured = {}

    class _Tokenizer:
        pad_token = "<pad>"
        eos_token = "</s>"
        model_max_length = 2048

    class _FastVisionModel:
        @staticmethod
        def from_pretrained(**kwargs):
            return object(), _Tokenizer()

        @staticmethod
        def get_peft_model(model, **kwargs):
            captured.update(kwargs)
            return model

    inst = mod.TrainVisionModel.__new__(mod.TrainVisionModel)
    inst.config = config
    original = mod.FastVisionModel if hasattr(mod, "FastVisionModel") else None
    mod.FastVisionModel = _FastVisionModel
    try:
        inst.prepare_model()
    finally:
        if original is not None:
            mod.FastVisionModel = original
    return captured


class TestLoraReadsTheConfig:

    def test_configured_values_reach_get_peft_model(self, mod):
        """The whole point of the fix: a value in the config must arrive at the
        adapter. A swapped key or a lingering literal would fail here."""
        kwargs = _peft_kwargs(mod, {
            "model_name": "v", "load_in_4bit": True,
            "lora_r": 8, "lora_alpha": 32, "lora_dropout": 0.05,
            "random_state": 123, "use_rslora": True,
        })
        assert kwargs["r"] == 8
        assert kwargs["lora_alpha"] == 32
        assert kwargs["lora_dropout"] == 0.05
        assert kwargs["random_state"] == 123
        assert kwargs["use_rslora"] is True

    def test_the_previous_literals_remain_the_defaults(self, mod):
        """An existing config that set none of these must train identically."""
        kwargs = _peft_kwargs(mod, {"model_name": "v", "load_in_4bit": True})
        assert kwargs["r"] == 16
        assert kwargs["lora_alpha"] == 16
        assert kwargs["lora_dropout"] == 0
        assert kwargs["random_state"] == 3407
        assert kwargs["use_rslora"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
