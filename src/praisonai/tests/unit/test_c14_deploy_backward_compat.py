"""C14 backward-compat: praisonai.deploy shims alias praisonai_deploy."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
DEPLOY_PKG = REPO / "src" / "praisonai-deploy"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (
        str(REPO / "src" / "praisonai-agents"),
        str(DEPLOY_PKG),
        str(WRAPPER_PKG),
        str(REPO / "src" / "praisonai-code"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_code, ensure_praisonai_deploy

    ensure_praisonai_deploy()
    ensure_praisonai_code()
    yield


class TestDeployModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.deploy.models", "praisonai_deploy.models"),
            ("praisonai.deploy.schema", "praisonai_deploy.schema"),
            ("praisonai.deploy.doctor", "praisonai_deploy.doctor"),
            ("praisonai.deploy.docker", "praisonai_deploy.docker"),
            ("praisonai.deploy.api", "praisonai_deploy.api"),
            ("praisonai.deploy.providers.aws", "praisonai_deploy.providers.aws"),
            ("praisonai.deploy.providers.azure", "praisonai_deploy.providers.azure"),
            ("praisonai.deploy.providers.gcp", "praisonai_deploy.providers.gcp"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_deploy_class_identity(self):
        from praisonai.deploy import Deploy as OldDeploy
        from praisonai_deploy import Deploy as NewDeploy

        assert OldDeploy is NewDeploy

    def test_get_deployment_status_identity(self):
        from praisonai.deploy import get_deployment_status as old_fn
        from praisonai_deploy import get_deployment_status as new_fn

        assert old_fn is new_fn

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_deploy"
        assert not nested.exists()

    def test_command_shim_identity(self):
        old_mod = importlib.import_module("praisonai.cli.commands.deploy")
        new_mod = importlib.import_module("praisonai_deploy.cli.commands.deploy")
        assert old_mod is new_mod

    def test_features_shim_identity(self):
        old_mod = importlib.import_module("praisonai.cli.features.deploy")
        new_mod = importlib.import_module("praisonai_deploy.cli.features.deploy")
        assert old_mod is new_mod

    def test_scheduler_shim_identity(self):
        old_mod = importlib.import_module("praisonai.scheduler.deployment")
        new_mod = importlib.import_module("praisonai_deploy.scheduler.deployment")
        assert old_mod is new_mod


class TestDeployBridge:
    def test_deploy_package_available(self):
        from praisonai_code._deploy_bridge import deploy_package_available

        assert deploy_package_available() is True

    def test_lazy_import_does_not_load_heavy_modules(self):
        for mod in ("main", "docker", "api"):
            sys.modules.pop(f"praisonai_deploy.{mod}", None)
        import praisonai_deploy  # noqa: F401

        assert "praisonai_deploy.main" not in sys.modules
        assert "praisonai_deploy.docker" not in sys.modules
        assert "praisonai_deploy.api" not in sys.modules


class TestDeployCliRouting:
    def test_deploy_typer_command_resolves(self):
        import click
        from praisonai_code.cli.app import app  # noqa: F401
        from typer.main import get_command as typer_get_command

        root = typer_get_command(app)
        ctx = click.Context(root)
        assert root.get_command(ctx, "deploy") is not None

    def test_deploy_run_and_doctor_commands(self):
        from praisonai_deploy.cli.commands import deploy as deploy_mod

        assert hasattr(deploy_mod, "deploy_run")
        assert hasattr(deploy_mod, "deploy_doctor")
