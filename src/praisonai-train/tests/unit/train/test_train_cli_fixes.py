"""Regression tests for three silent-data-loss bugs in praisonai-train.

Each test pins a specific failure described in the issue:

1. ``train llm <dataset>`` forwarded the path as a bare positional, which the
   legacy dispatcher dropped — training silently ran on yahma/alpaca-cleaned.
2. ``generate`` truncated an existing output file to zero bytes when every
   teacher request failed (the all-failures path still opened it "w").
3. Every Ollama Modelfile shipped an indented ``TEMPLATE``, so the served
   prompt format differed from the trained one.

All run offline: the generator is stubbed and the Modelfile builder needs only
``config`` (no torch/unsloth).
"""
from pathlib import Path
from unittest.mock import patch

import pytest
import typer


# --- Bug 1: the dataset argument must reach the trainer as --dataset ----------

def test_train_llm_forwards_dataset_as_option():
    """The user's dataset must be passed as --dataset, not a dropped positional."""
    from praisonai_train.cli.commands import train as train_cmd

    captured = {}

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            import sys
            captured["argv"] = list(sys.argv)

        def main(self):
            pass

    class _FakeModule:
        PraisonAI = _FakePraisonAI

    # ``import_code_module``/``code_available`` are imported inside the function
    # from the bridge module, so patch them at their source.
    with patch("praisonai_train._code_bridge.import_code_module",
               return_value=_FakeModule()):
        train_cmd.train_llm(
            "/data/my_tamil_sft.jsonl", model="unsloth/Llama-3.1-8B", verbose=False)

    argv = captured["argv"]
    # The dataset arrives as the value of --dataset (what the train branch reads),
    # so it can no longer land in unknown_args and be discarded.
    assert "--dataset" in argv
    assert argv[argv.index("--dataset") + 1] == "/data/my_tamil_sft.jsonl"
    # The model option still arrives (its presence is what made the bug invisible).
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "unsloth/Llama-3.1-8B"


# --- Bug 2: an all-failures generate run must not destroy an existing file ----

def test_generate_all_failures_does_not_truncate_existing_output(tmp_path):
    """When no rows are produced, a pre-existing corpus is left byte-for-byte."""
    from praisonai_train.cli.commands import data as data_cmd

    out = tmp_path / "corpus.jsonl"
    original = '{"instruction": "PRECIOUS ROW 1"}\n{"instruction": "PRECIOUS ROW 2"}\n'
    out.write_text(original)

    # Simulate every teacher request failing: the generator yields nothing.
    def empty_generator(cfg, progress_callback=None):
        return iter(())

    with patch("praisonai_train.data.generate_dataset", empty_generator):
        with pytest.raises(typer.Exit):
            data_cmd.generate_data(
                config=None, output=str(out), recipe=None, deployment=None,
                num=2, concurrency=None, start_offset=None, snapshot_every=None,
            )

    # The original file survives untouched — the whole point of the fix.
    assert out.exists()
    assert out.read_text() == original
    # No stray temp files were left behind in the directory.
    assert not list(tmp_path.glob("*.tmp"))


def test_generate_success_writes_rows(tmp_path):
    """The happy path still writes the generated rows to the output file."""
    from praisonai_train.cli.commands import data as data_cmd

    out = tmp_path / "corpus.jsonl"

    def two_rows(cfg, progress_callback=None):
        yield {"instruction": "a"}
        yield {"instruction": "b"}

    with patch("praisonai_train.data.generate_dataset", two_rows):
        data_cmd.generate_data(
            config=None, output=str(out), recipe=None, deployment=None,
            num=2, concurrency=None, start_offset=None, snapshot_every=None,
        )

    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert not list(tmp_path.glob("*.tmp"))


# --- Bug 3: the Ollama Modelfile TEMPLATE must not be indented ----------------

def _modelfile_for(model_name):
    from praisonai_train.train.llm.trainer import TrainModel

    obj = TrainModel.__new__(TrainModel)
    obj.config = {"hf_model_name": "lora_model", "model_name": model_name}
    return obj.prepare_modelfile_content()


def test_ollama_modelfile_template_is_not_indented():
    """Continuation lines must sit at column 0, matching the trained format."""
    content = _modelfile_for("unsloth/gemma-2-9b")

    # The trained format has an un-indented model turn; the served one must match.
    assert "\n<start_of_turn>model" in content
    assert "\n    <start_of_turn>model" not in content
    # The Modelfile directives themselves are also at column 0.
    assert content.startswith("FROM ")
    assert "\nTEMPLATE " in content
