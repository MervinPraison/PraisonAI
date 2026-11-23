"""`praisonai-train llm` starts its own trainer; no praisonai-code or wrapper needed."""
import subprocess
import sys
from unittest.mock import patch

import pytest
import typer

from praisonai_train.train.llm import launch as launch_mod


def test_standard_model_runs_the_package_trainer():
    assert launch_mod.trainer_invocation({"model_name": "unsloth/Llama-3.2-1B"}) == [
        "-m", "praisonai_train.train.llm.trainer", "train"]


def test_vision_model_runs_the_packaged_vision_script():
    invocation = launch_mod.trainer_invocation({"model_name": "unsloth/Qwen2-VL-7B"})
    assert invocation[0].endswith("train_vision.py") and invocation[1] == "train"


def _ready_deps(monkeypatch):
    monkeypatch.setattr(launch_mod.importlib.util, "find_spec", lambda name: object())


def test_uses_conda_env_when_present(monkeypatch):
    _ready_deps(monkeypatch)
    monkeypatch.setattr(launch_mod, "_conda_env_ready", lambda: True)
    with patch.object(launch_mod, "_stream") as stream:
        launch_mod.launch({"model_name": "m"})
    command = stream.call_args.args[0]
    assert command[:5] == ["conda", "run", "--no-capture-output", "--name", "praison_env"]
    assert command[-3:] == ["-m", "praisonai_train.train.llm.trainer", "train"]


def test_falls_back_to_this_python_when_conda_run_fails(monkeypatch):
    _ready_deps(monkeypatch)
    monkeypatch.setattr(launch_mod, "_conda_env_ready", lambda: True)
    calls = []

    def fake_stream(command, env):
        calls.append(command)
        if command[0] == "conda":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(launch_mod, "_stream", fake_stream)
    launch_mod.launch({"model_name": "m"})
    assert calls[-1][:2] == [sys.executable, "-u"]


def test_without_conda_runs_this_python(monkeypatch):
    _ready_deps(monkeypatch)
    monkeypatch.setattr(launch_mod, "_conda_env_ready", lambda: False)
    with patch.object(launch_mod, "_stream") as stream:
        launch_mod.launch({"model_name": "m"})
    assert stream.call_args.args[0][:2] == [sys.executable, "-u"]
    assert stream.call_args.args[1]["PYTHONUNBUFFERED"] == "1"


def test_missing_training_stack_is_reported(monkeypatch):
    monkeypatch.setattr(launch_mod.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(launch_mod.TrainingDepsMissing):
        launch_mod.launch({"model_name": "m"})


def test_llm_command_reports_missing_training_stack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from praisonai_train.cli.commands import train as train_cmd

    monkeypatch.setattr(launch_mod.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(typer.Exit) as excinfo:
        train_cmd.train_llm("data.jsonl", model=None, verbose=False)
    assert excinfo.value.exit_code == 1


def test_llm_command_runs_without_praisonai_code_or_wrapper(tmp_path, monkeypatch):
    """The command reaches the trainer even when neither package is importable."""
    monkeypatch.chdir(tmp_path)
    for name in ("praisonai_code", "praisonai"):
        monkeypatch.setitem(sys.modules, name, None)  # import now raises ImportError
    from praisonai_train.cli.commands import train as train_cmd

    with patch.object(launch_mod, "launch") as launched:
        train_cmd.train_llm("data.jsonl", model=None, verbose=False)
    launched.assert_called_once()
    assert (tmp_path / "config.yaml").exists()

