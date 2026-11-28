"""Start local LLM fine-tuning from praisonai-train itself.

Runs the trainer in the ``praison_env`` conda environment when conda has it,
otherwise with this Python. The trainer reads ``./config.yaml``, which the
caller writes first. Same steps as the legacy ``praisonai train`` dispatcher,
without needing praisonai-code or the praisonai wrapper.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from typing import List, Mapping

_VISION_MARKERS = ("-vl-", "-vl", "vl-", "-vision-", "-vision", "vision-", "visionmodel")
_CONDA_ENV = "praison_env"


class TrainingDepsMissing(ImportError):
    """The local fine-tuning stack (unsloth) is not installed."""


def trainer_invocation(config: Mapping) -> List[str]:
    """Arguments after ``python -u`` that start the right trainer for the model."""
    model = str(config.get("model_name", "")).lower()
    if any(marker in model for marker in _VISION_MARKERS):
        import praisonai_train

        root = os.path.dirname(os.path.abspath(praisonai_train.__file__))
        return [os.path.join(root, "train_vision.py"), "train"]
    return ["-m", "praisonai_train.train.llm.trainer", "train"]


def _stream(command: List[str], env: Mapping[str, str]) -> None:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, env=dict(env))
    for line in process.stdout:
        print(line, end="")
    process.stdout.close()
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, command)


def _conda_has_env() -> bool:
    return _CONDA_ENV in subprocess.check_output(["conda", "env", "list"]).decode("utf-8")


def _conda_env_ready() -> bool:
    """True when ``praison_env`` exists, creating it once if conda is present."""
    try:
        if _conda_has_env():
            print(f"Conda environment '{_CONDA_ENV}' found.")
            return True
        print(f"Conda environment '{_CONDA_ENV}' not found. Setting it up...")
        from praisonai_train.setup.setup_conda_env import main as setup_conda_env

        setup_conda_env()
        return _conda_has_env()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Conda not available or failed to check environment.")
        return False


def launch(config: Mapping) -> None:
    """Run the trainer for ``config``; raises ``CalledProcessError`` if it fails."""
    if importlib.util.find_spec("unsloth") is None:
        raise TrainingDepsMissing("unsloth is not installed")
    invocation = trainer_invocation(config)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if _conda_env_ready():
        try:
            print("Attempting to run training using conda environment...")
            _stream(["conda", "run", "--no-capture-output", "--name", _CONDA_ENV,
                     "python", "-u", *invocation], env)
            return
        except subprocess.CalledProcessError as exc:
            print(f"Conda run failed with error: {exc}")
            print("Falling back to direct Python execution...")
    else:
        print("Conda environment not available, using direct Python execution...")
    _stream([sys.executable, "-u", *invocation], env)
