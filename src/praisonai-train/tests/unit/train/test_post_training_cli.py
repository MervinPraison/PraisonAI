"""Two questions every fine-tune ends with, neither of which had an answer.

**What did it save?** After an interrupted run there was no way to find the
checkpoints without `ls`, and `export --model-dir` requires you to already know
the path.

**Did it work?** `TrainModel.inference()` has existed for a while with no
caller anywhere in the package — dead code for the single most common thing a
user wants next. `serve --benchmark` measures tokens per second without showing
a single token, and `benchmark` measures remote API deployments, not the model
you just trained. The only way to see output was to write Python.

Also here: a command-name collision that silently replaced one command with
another, caught by asserting both survive registration.
"""

import json

import pytest
from typer.testing import CliRunner

from praisonai_train.cli import app as app_mod
from praisonai_train.cli.commands import run as run_cmd

runner = CliRunner()


def _make(root, *steps, junk=()):
    for s in steps:
        d = root / f"checkpoint-{s}"
        d.mkdir(parents=True)
        (d / "adapter_model.safetensors").write_bytes(b"x" * 1024)
    for name in junk:
        (root / name).mkdir(parents=True)
    return root


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
def test_both_new_commands_are_registered():
    names = {c.name or c.callback.__name__ for c in app_mod.app.registered_commands}
    assert {"checkpoints", "infer"} <= names


def test_infer_did_not_displace_dataset_generation():
    """A collision here is silent.

    `generate` was already dataset generation. Registering a second command of
    the same name replaces one with the other and nothing says so.
    """
    names = [c.name or c.callback.__name__ for c in app_mod.app.registered_commands]
    assert "generate" in names, "dataset generation was displaced"
    assert len(names) == len(set(names)), f"duplicate command names: {names}"


# --------------------------------------------------------------------------- #
# checkpoints
# --------------------------------------------------------------------------- #
def test_checkpoints_are_listed_newest_first(tmp_path):
    _make(tmp_path, 100, 500, 200)
    found = run_cmd.find_checkpoints(tmp_path)
    assert [c["step"] for c in found] == [500, 200, 100]


def test_steps_sort_numerically_not_lexically(tmp_path):
    # "checkpoint-1000" sorts before "checkpoint-200" as a string.
    _make(tmp_path, 200, 1000)
    assert [c["step"] for c in run_cmd.find_checkpoints(tmp_path)] == [1000, 200]


def test_only_real_checkpoint_directories_count(tmp_path):
    # A directory someone called "checkpoint-final" must not be reported as
    # step 0, and unrelated output must not be listed at all.
    _make(tmp_path, 50, junk=("checkpoint-final", "runs", "logs"))
    found = run_cmd.find_checkpoints(tmp_path)
    assert [c["step"] for c in found] == [50]


def test_a_missing_directory_is_empty_rather_than_an_exception(tmp_path):
    assert run_cmd.find_checkpoints(tmp_path / "never-existed") == []


def test_the_size_is_measured_not_guessed(tmp_path):
    _make(tmp_path, 10)
    assert run_cmd.find_checkpoints(tmp_path)[0]["bytes"] == 1024


def test_no_checkpoints_exits_non_zero_with_a_remedy(tmp_path):
    result = runner.invoke(app_mod.app, ["checkpoints", "-d", str(tmp_path)])
    assert result.exit_code == 1
    assert "save_steps" in result.output, "the remedy does not say how to get any"


def test_json_output_is_machine_readable(tmp_path):
    _make(tmp_path, 300)
    result = runner.invoke(app_mod.app, ["checkpoints", "-d", str(tmp_path), "--json"])
    assert json.loads(result.output)[0]["step"] == 300


def test_the_human_listing_names_the_newest(tmp_path):
    _make(tmp_path, 100, 900)
    result = runner.invoke(app_mod.app, ["checkpoints", "-d", str(tmp_path)])
    assert "step 900" in result.output


# --------------------------------------------------------------------------- #
# infer
# --------------------------------------------------------------------------- #
def test_infer_streams_rather_than_returning_one_lump():
    import inspect

    src = inspect.getsource(run_cmd.infer)
    assert "TextStreamer" in src, (
        "output is not streamed; on a large model the first token is the answer "
        "to 'is this alive' and arrives long before the last")
    assert "skip_prompt=True" in src, "the prompt is echoed back at the user"


def test_infer_refuses_a_directory_that_is_not_there(tmp_path):
    result = runner.invoke(app_mod.app, [
        "infer", "hello", "-d", str(tmp_path / "nope")])
    assert result.exit_code != 0


def test_infer_exposes_the_knobs_that_change_the_answer():
    import inspect

    params = inspect.signature(run_cmd.infer).parameters
    for knob in ("max_new_tokens", "temperature", "max_seq_length", "load_in_4bit"):
        assert knob in params, f"{knob} is hardcoded"


def test_the_defaults_are_usable_rather_than_experimental():
    import inspect

    params = inspect.signature(run_cmd.infer).parameters
    # Typer wraps a default in OptionInfo, so the value is one level down --
    # reading .default directly compares against the wrapper and passes for
    # any number at all.
    def value(name):
        d = params[name].default
        return getattr(d, "default", d)

    # The dead inference() used temperature=1.5 and max_new_tokens=64 — good
    # for a demo, wrong for "did my fine-tune take".
    assert value("temperature") <= 1.0
    assert value("max_new_tokens") >= 128
