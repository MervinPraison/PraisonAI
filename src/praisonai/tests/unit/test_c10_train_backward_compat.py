"""C10 backward-compat: praisonai.train shims alias praisonai_train."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TRAIN_PKG = REPO / "src" / "praisonai-train"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (str(REPO / "src" / "praisonai-agents"), str(TRAIN_PKG), str(WRAPPER_PKG)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_code, ensure_praisonai_train

    ensure_praisonai_train()
    ensure_praisonai_code()
    yield


class TestTrainModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.train.agents.models", "praisonai_train.train.agents.models"),
            ("praisonai.train.agents.storage", "praisonai_train.train.agents.storage"),
            ("praisonai.train.agents.grader", "praisonai_train.train.agents.grader"),
            ("praisonai.train.agents.hook", "praisonai_train.train.agents.hook"),
            ("praisonai.train.agents.orchestrator", "praisonai_train.train.agents.orchestrator"),
            ("praisonai.train.llm.trainer", "praisonai_train.train.llm.trainer"),
            ("praisonai.train._ollama", "praisonai_train.train._ollama"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_trainer_class_identity(self):
        from praisonai.train.agents import AgentTrainer as OldTrainer
        from praisonai_train.train.agents import AgentTrainer as NewTrainer

        assert OldTrainer is NewTrainer

    def test_scenario_class_identity(self):
        from praisonai.train.agents import TrainingScenario as OldScenario
        from praisonai_train.train.agents import TrainingScenario as NewScenario

        assert OldScenario is NewScenario

    def test_apply_training_identity(self):
        from praisonai.train.agents import apply_training as old_apply
        from praisonai_train.train.agents import apply_training as new_apply

        assert old_apply is new_apply

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_train"
        assert not nested.exists()

    def test_command_shim_identity(self):
        old_mod = importlib.import_module("praisonai.cli.commands.train")
        new_mod = importlib.import_module("praisonai_train.cli.commands.train")
        assert old_mod is new_mod

    def test_train_vision_shim_identity(self):
        old_mod = importlib.import_module("praisonai.train_vision")
        new_mod = importlib.import_module("praisonai_train.train_vision")
        assert old_mod is new_mod

    def test_upload_vision_shim_identity(self):
        old_mod = importlib.import_module("praisonai.upload_vision")
        new_mod = importlib.import_module("praisonai_train.upload_vision")
        assert old_mod is new_mod


class TestTrainLazyImports:
    """The C10 move must not regress lazy ML imports (see test_lazy_imports.py)."""

    @pytest.mark.parametrize("module", ["praisonai_train", "praisonai_train.train.llm.trainer"])
    def test_import_pulls_no_heavy_deps(self, module: str):
        heavy = ("torch", "unsloth", "trl", "datasets", "transformers")
        already = {name for name in heavy if name in sys.modules}
        importlib.import_module(module)
        pulled = [name for name in heavy if name in sys.modules and name not in already]
        assert not pulled, f"{module} eagerly imported heavy deps: {pulled}"

    def test_top_level_lazy_exports(self):
        import praisonai_train

        assert hasattr(praisonai_train, "__version__")
        trainer_cls = praisonai_train.AgentTrainer
        assert trainer_cls.__name__ == "AgentTrainer"


class TestTrainCliRouting:
    def test_train_resident_commands_declared(self):
        from praisonai_code.cli import app as code_app

        assert "train" in code_app._TRAIN_RESIDENT_COMMANDS
        assert "train" not in code_app._WRAPPER_RESIDENT_COMMANDS

    def test_train_bridge_available(self):
        from praisonai_code._train_bridge import train_package_available

        assert train_package_available() is True

    def test_get_command_resolves_train(self):
        import click
        from praisonai_code.cli.app import LazyCommandGroup, app  # noqa: F401
        from typer.main import get_command as typer_get_command

        root = typer_get_command(app)
        ctx = click.Context(root)
        cmd = root.get_command(ctx, "train")
        assert cmd is not None
