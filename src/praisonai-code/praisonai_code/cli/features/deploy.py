"""Bridge deploy CLI features from praisonai-deploy."""

from __future__ import annotations

from praisonai_code._deploy_bridge import import_deploy_module


def handle_deploy_command(args):
    mod = import_deploy_module("praisonai_deploy.cli.features.deploy")
    return mod.handle_deploy_command(args)


def __getattr__(name: str):
    if name == "DeployHandler":
        mod = import_deploy_module("praisonai_deploy.cli.features.deploy")
        return mod.DeployHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
