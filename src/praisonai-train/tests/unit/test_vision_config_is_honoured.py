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
import sys
import types

import pytest


@pytest.fixture(scope="module")
def cls():
    """Load train_vision with its GPU-only dependencies stubbed."""
    for name in ("torch", "unsloth", "transformers", "datasets", "trl", "peft"):
        module = types.ModuleType(name)
        module.__version__ = "0.0-stub"
        sys.modules.setdefault(name, module)
    spec = importlib.util.spec_from_file_location(
        "train_vision_under_test", "praisonai_train/train_vision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TrainVisionModel


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


class TestLoraReadsTheConfig:

    def test_the_literals_are_gone(self, cls):
        import inspect
        src = inspect.getsource(cls.prepare_model)
        assert "r=16," not in src, "LoRA rank is still hardcoded"
        assert 'self.config.get("lora_r"' in src

    def test_the_previous_literals_remain_the_defaults(self, cls):
        import inspect
        src = inspect.getsource(cls.prepare_model)
        for default in ('"lora_r", 16', '"lora_alpha", 16', '"random_state", 3407'):
            assert default in src, f"default changed: {default}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
