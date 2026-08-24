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


def test_train_llm_propagates_nonzero_exit():
    """A failed router run (e.g. missing deps) must not be swallowed as exit 0.

    The router raises ``SystemExit(1)`` when training dependencies are absent;
    ``train_llm`` must re-raise a non-zero ``typer.Exit`` so callers / CI gating
    on ``$?`` see the failure instead of a false green.
    """
    from praisonai_train.cli.commands import train as train_cmd

    class _ExitingPraisonAI:
        def __init__(self, *a, **k):
            pass

        def main(self):
            raise SystemExit(1)

    class _FakeModule:
        PraisonAI = _ExitingPraisonAI

    with patch("praisonai_train._code_bridge.import_code_module",
               return_value=_FakeModule()):
        with pytest.raises(typer.Exit) as excinfo:
            train_cmd.train_llm("/data/ds.jsonl", model=None, verbose=False)

    assert excinfo.value.exit_code == 1


def test_train_llm_swallows_clean_exit():
    """A clean ``SystemExit(0)`` from the router still returns 0 (no raise)."""
    from praisonai_train.cli.commands import train as train_cmd

    class _CleanExitPraisonAI:
        def __init__(self, *a, **k):
            pass

        def main(self):
            raise SystemExit(0)

    class _FakeModule:
        PraisonAI = _CleanExitPraisonAI

    with patch("praisonai_train._code_bridge.import_code_module",
               return_value=_FakeModule()):
        # Must not raise: a clean exit is a success.
        train_cmd.train_llm("/data/ds.jsonl", model=None, verbose=False)


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


def test_generate_output_is_not_locked_to_0600(tmp_path):
    """The atomic mkstemp swap must not leave the corpus at owner-only 0600.

    ``mkstemp`` creates 0600 and ``os.replace`` would make that final, stripping
    group/other read a plain ``open(..., "w")`` would have granted via umask and
    locking downstream validation/training jobs out of a shared dataset.
    """
    import os

    from praisonai_train.cli.commands import data as data_cmd

    out = tmp_path / "corpus.jsonl"

    def one_row(cfg, progress_callback=None):
        yield {"instruction": "a"}

    with patch("praisonai_train.data.generate_dataset", one_row):
        data_cmd.generate_data(
            config=None, output=str(out), recipe=None, deployment=None,
            num=1, concurrency=None, start_offset=None, snapshot_every=None,
        )

    mode = os.stat(out).st_mode & 0o777
    umask = os.umask(0)
    os.umask(umask)
    expected = 0o666 & ~umask
    assert mode == expected, f"expected {oct(expected)}, got {oct(mode)}"


def test_generate_preserves_existing_output_mode(tmp_path):
    """Overwriting an existing corpus keeps that file's original permissions."""
    import os

    from praisonai_train.cli.commands import data as data_cmd

    out = tmp_path / "corpus.jsonl"
    out.write_text('{"instruction": "old"}\n')
    os.chmod(out, 0o640)

    def one_row(cfg, progress_callback=None):
        yield {"instruction": "new"}

    with patch("praisonai_train.data.generate_dataset", one_row):
        data_cmd.generate_data(
            config=None, output=str(out), recipe=None, deployment=None,
            num=1, concurrency=None, start_offset=None, snapshot_every=None,
        )

    assert os.stat(out).st_mode & 0o777 == 0o640


def test_generate_preserves_symlink_output(tmp_path):
    """A symlink destination stays a link; its target receives the new rows.

    ``os.replace`` would otherwise clobber the link itself, leaving consumers
    that read through it staring at the stale target.
    """
    import os

    from praisonai_train.cli.commands import data as data_cmd

    real = tmp_path / "real_corpus.jsonl"
    real.write_text('{"instruction": "old"}\n')
    link = tmp_path / "corpus.jsonl"
    os.symlink(real, link)

    def one_row(cfg, progress_callback=None):
        yield {"instruction": "new"}

    with patch("praisonai_train.data.generate_dataset", one_row):
        data_cmd.generate_data(
            config=None, output=str(link), recipe=None, deployment=None,
            num=1, concurrency=None, start_offset=None, snapshot_every=None,
        )

    # The link is intact and still points at the real file.
    assert os.path.islink(link)
    assert os.path.realpath(link) == os.path.realpath(real)
    # The rows landed on the target consumers actually read through the link.
    lines = [ln for ln in real.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "new" in real.read_text()
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
