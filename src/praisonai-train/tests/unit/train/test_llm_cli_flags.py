"""`praisonai-train llm` took three flags to `unsloth train`'s thirty-eight.

Worse, it was the one command that would not accept `--config` — `export` and
`serve` both do — so changing a LoRA rank meant hand-editing a YAML file the
CLI gave you no way to point at.

And there was no `--dry-run`, though `agents` has one. On a rented GPU box,
"show me what you are about to do" is the difference between a caught typo and
a wasted hour.
"""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from praisonai_train.cli import app as app_mod
from praisonai_train.cli.commands import train as train_cmd

runner = CliRunner()


def _write(tmp_path, **cfg):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def _dry(args):
    result = runner.invoke(app_mod.app, ["llm", *args, "--dry-run"])
    assert result.exit_code == 0, result.output
    body = result.output.split("\n#")[0]
    return yaml.safe_load(body) or {}


# --------------------------------------------------------------------------- #
# --config, which llm alone refused
# --------------------------------------------------------------------------- #
def test_llm_accepts_a_config_file(tmp_path):
    cfg = _write(tmp_path, model_name="unsloth/gemma-2-2b-it-bnb-4bit", lora_r=16)
    assert _dry(["-c", str(cfg)])["lora_r"] == 16


def test_a_flag_overrides_the_file(tmp_path):
    # The precedence has to be this way round: the file is the baseline and the
    # flag is the thing you just typed.
    cfg = _write(tmp_path, lora_r=16, max_seq_length=2048)
    resolved = _dry(["-c", str(cfg), "--lora-r", "32"])
    assert resolved["lora_r"] == 32
    assert resolved["max_seq_length"] == 2048, "an untouched key was lost"


def test_flags_work_with_no_config_at_all(tmp_path):
    resolved = _dry(["data.jsonl", "--lora-r", "8", "--epochs", "3"])
    assert resolved["lora_r"] == 8
    assert resolved["num_train_epochs"] == 3
    assert resolved["dataset"] == "data.jsonl"


def test_a_config_that_is_not_a_mapping_is_refused(tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("- just\n- a\n- list\n")
    result = runner.invoke(app_mod.app, ["llm", "-c", str(bad), "--dry-run"])
    assert result.exit_code == 1
    assert "mapping" in result.output


# --------------------------------------------------------------------------- #
# --dry-run
# --------------------------------------------------------------------------- #
def test_dry_run_does_not_train(tmp_path, monkeypatch):
    # The whole point: it must not reach the training runner.
    called = []
    monkeypatch.setattr(train_cmd, "_print_resolved_config",
                        lambda *a, **k: called.append("printed"))
    result = runner.invoke(app_mod.app, ["llm", "data.jsonl", "--dry-run"])
    assert result.exit_code == 0
    assert called == ["printed"], "dry-run went past the preview"


def test_dry_run_says_which_values_came_from_flags(tmp_path):
    cfg = _write(tmp_path, lora_r=16)
    result = runner.invoke(app_mod.app, [
        "llm", "-c", str(cfg), "--lora-r", "32", "--epochs", "2", "--dry-run"])
    assert "lora_r" in result.output and "num_train_epochs" in result.output
    assert "came from flags" in result.output


def test_dry_run_output_is_valid_yaml(tmp_path):
    # It should be pasteable back into a config file.
    cfg = _write(tmp_path, model_name="m", max_seq_length=2048)
    assert _dry(["-c", str(cfg), "--lora-r", "8"])["max_seq_length"] == 2048


# --------------------------------------------------------------------------- #
# The flags themselves
# --------------------------------------------------------------------------- #
def test_every_flag_maps_to_a_config_key_that_exists():
    from praisonai_train.train.llm.trainer import TrainModel

    for name, flag, _help in train_cmd._TRAIN_FLAGS:
        assert name in TrainModel.KNOWN_KEYS, (
            f"{flag} sets '{name}', which the config does not accept")


def test_the_flags_cover_what_a_run_is_usually_tuned_by():
    names = {name for name, _f, _h in train_cmd._TRAIN_FLAGS}
    assert {"method", "max_seq_length", "learning_rate", "lora_r",
            "per_device_train_batch_size", "max_steps"} <= names


def test_a_dataset_is_still_required_when_no_config_names_one():
    # The argument became optional so --config can supply it; that must not
    # turn "I forgot the dataset" into a run against the default corpus.
    result = runner.invoke(app_mod.app, ["llm"])
    assert result.exit_code == 1
    assert "dataset" in result.output.lower()


def test_the_dataset_reaches_the_trainer_via_the_written_config(tmp_path, monkeypatch):
    """The incident this file's sibling comment describes, now fixed at the root.

    The legacy dispatcher reads only ./config.yaml and drops flags it does not
    declare (parse_known_args), so forwarding --dataset/--lora-r/etc. could not
    make the real run match the preview. Instead the resolved config is written
    to the config.yaml the dispatcher loads, with a string dataset normalised to
    the [{name: ...}] shape the trainer requires. Assert that end state so the
    dataset can never again be silently dropped.
    """
    import types

    import yaml

    monkeypatch.chdir(tmp_path)

    # Replace the heavy runner with a stub whose main() records that it ran; the
    # config.yaml it would read has already been written by the time it is called.
    ran = []

    class _StubPraisonAI:
        def main(self):
            ran.append(Path.cwd() / "config.yaml")

    fake_module = types.SimpleNamespace(PraisonAI=_StubPraisonAI)

    import praisonai_train._code_bridge as bridge
    monkeypatch.setattr(bridge, "import_code_module", lambda _name: fake_module)
    monkeypatch.setattr(bridge, "code_available", lambda: True)

    result = runner.invoke(app_mod.app, ["llm", "data.jsonl", "--lora-r", "8"])
    assert result.exit_code == 0, result.output
    assert ran, "the runner was never reached"

    written = tmp_path / "config.yaml"
    assert written.exists(), "the resolved config.yaml was not written"
    cfg = yaml.safe_load(written.read_text())
    assert cfg["dataset"] == [{"name": "data.jsonl"}], (
        "dataset must be normalised to the shape the trainer iterates")
    assert cfg["lora_r"] == 8, "a tuning flag did not reach the written config"
