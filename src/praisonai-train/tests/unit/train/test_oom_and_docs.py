"""Two things the tool told the user that were not true.

**OOM.** `torch.cuda.OutOfMemoryError` subclasses `RuntimeError`, so the CLI's
catch-all flattened it into a single `ERROR:` line carrying torch's raw
allocator dump. It is the most common fine-tuning failure and the one where a
first-time user has no idea which number to change.

**The README.** Two quickstart commands did not exist as written. One of them,
`praisonai-train llm --dataset ...`, is the exact shape of an incident the code
already carries a comment about: a dataset passed the wrong way was silently
dropped and the run trained on the default corpus, discovered only after the
GPU time was spent.
"""

import re
import subprocess
from pathlib import Path

import pytest

from praisonai_train.train.llm import trainer as trainer_mod


# --------------------------------------------------------------------------- #
# OOM classification
# --------------------------------------------------------------------------- #
class _TorchLikeOOM(RuntimeError):
    """Stands in for torch.cuda.OutOfMemoryError, matched by class name."""


_TorchLikeOOM.__name__ = "OutOfMemoryError"


@pytest.mark.parametrize("exc", [
    RuntimeError("CUDA out of memory. Tried to allocate 20.00 MiB"),
    RuntimeError("HIP out of memory"),
    RuntimeError("torch.OutOfMemoryError: out of memory"),
])
def test_every_runtimes_phrasing_is_recognised(exc):
    assert trainer_mod.is_out_of_memory(exc) is True


def test_the_class_name_is_matched_even_without_the_words():
    """torch has raised OOM with a message saying only "Tried to allocate ...".

    The class name is folded into the searched text for exactly this case.
    """
    bare = _TorchLikeOOM("Tried to allocate 2.00 GiB (GPU 0; 23.99 GiB total)")
    assert "out of memory" not in str(bare).lower(), "the fixture leaks a text marker"
    assert trainer_mod.is_out_of_memory(bare) is True


@pytest.mark.parametrize("exc", [
    ValueError("Config is missing required keys: ['model_name']"),
    RuntimeError("Hugging Face rejected the credentials"),
    RuntimeError("no such file or directory"),
])
def test_unrelated_failures_are_not_misreported_as_oom(exc):
    # Attaching "lower your batch size" to a missing-config error would send
    # someone down the wrong path entirely.
    assert trainer_mod.is_out_of_memory(exc) is False


def test_the_remedy_names_settings_that_exist():
    remedy = trainer_mod.OOM_REMEDIATION
    for knob in ("max_seq_length", "use_gradient_checkpointing",
                 "per_device_train_batch_size", "gradient_accumulation_steps",
                 "load_in_4bit"):
        assert knob in remedy, f"the remedy mentions no {knob}"
        assert knob in trainer_mod.TrainModel.KNOWN_KEYS, (
            f"the remedy suggests {knob}, which the config does not accept")


def test_the_remedy_is_ordered_cheapest_first():
    # Sequence length is the biggest lever and the least destructive change;
    # "use a smaller model" is the last resort and must not lead.
    remedy = trainer_mod.OOM_REMEDIATION
    assert remedy.index("max_seq_length") < remedy.index("smaller model")
    assert re.search(r"1\..*max_seq_length", remedy), "the list is not numbered in order"


def test_the_cli_attaches_the_remedy_only_to_oom():
    import inspect

    src = inspect.getsource(trainer_mod)
    handler = src[src.index("except (ValueError, RuntimeError"):]
    assert "is_out_of_memory(exc)" in handler, "the handler does not classify"
    assert "OOM_REMEDIATION" in handler, "the remedy is never printed"


# --------------------------------------------------------------------------- #
# The README's commands must exist
# --------------------------------------------------------------------------- #
README = Path(__file__).resolve().parents[3] / "README.md"


def _documented_commands():
    """Every `praisonai-train <sub>` invocation the README shows."""
    text = README.read_text()
    return sorted({m.group(1) for m in
                   re.finditer(r"praisonai-train\s+([a-z][a-z0-9-]*)", text)})


def test_every_command_the_readme_shows_is_registered():
    from praisonai_train.cli.app import app

    registered = {c.name or c.callback.__name__ for c in app.registered_commands}
    for name in _documented_commands():
        assert name in registered, (
            f"README documents `praisonai-train {name}`, which is not a command. "
            f"Registered: {sorted(registered)}")


def test_the_readme_does_not_pass_the_dataset_as_an_option():
    # `dataset` is a positional argument. `--dataset` fails outright — and a
    # reader who "fixes" it by dropping the flag hits the silent-default bug
    # the code comments were written to prevent.
    assert "praisonai-train llm --dataset" not in README.read_text()
