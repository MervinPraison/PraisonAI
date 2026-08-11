"""C13 backward-compat: praisonai.sandbox shims alias praisonai_sandbox."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SANDBOX_PKG = REPO / "src" / "praisonai-sandbox"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (
        str(REPO / "src" / "praisonai-agents"),
        str(SANDBOX_PKG),
        str(WRAPPER_PKG),
        str(REPO / "src" / "praisonai-code"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_code, ensure_praisonai_sandbox

    ensure_praisonai_sandbox()
    ensure_praisonai_code()
    yield


class TestSandboxModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.sandbox.docker", "praisonai_sandbox.docker"),
            ("praisonai.sandbox.subprocess", "praisonai_sandbox.subprocess"),
            ("praisonai.sandbox._registry", "praisonai_sandbox._registry"),
            ("praisonai.sandbox.e2b", "praisonai_sandbox.e2b"),
            ("praisonai.sandbox.sandlock", "praisonai_sandbox.sandlock"),
            ("praisonai.sandbox.ssh", "praisonai_sandbox.ssh"),
            ("praisonai.sandbox.modal", "praisonai_sandbox.modal"),
            ("praisonai.sandbox.daytona", "praisonai_sandbox.daytona"),
            ("praisonai.sandbox._compat", "praisonai_sandbox._compat"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_docker_sandbox_class_identity(self):
        from praisonai.sandbox import DockerSandbox as OldCls
        from praisonai_sandbox import DockerSandbox as NewCls

        assert OldCls is NewCls

    @pytest.mark.parametrize(
        "name",
        ["SubprocessSandbox", "E2BSandbox", "ModalSandbox", "DaytonaSandbox"],
    )
    def test_lazy_class_exports(self, name: str):
        from praisonai_sandbox import __getattr__ as lazy_get

        cls = lazy_get(name)
        from praisonai.sandbox import __getattr__ as shim_get

        assert shim_get(name) is cls

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_sandbox"
        assert not nested.exists()


class TestSandboxBridge:
    def test_sandbox_package_available(self):
        from praisonaiagents.sandbox._sandbox_bridge import sandbox_package_available

        assert sandbox_package_available() is True

    def test_lazy_import_does_not_load_heavy_backends(self):
        for mod in ("docker", "modal", "e2b"):
            sys.modules.pop(f"praisonai_sandbox.{mod}", None)
        import praisonai_sandbox  # noqa: F401

        assert "praisonai_sandbox.docker" not in sys.modules
        assert "praisonai_sandbox.modal" not in sys.modules
        assert "praisonai_sandbox.e2b" not in sys.modules

    def test_resolve_subprocess_class(self):
        from praisonaiagents.sandbox._sandbox_bridge import resolve_sandbox_class
        from praisonai_sandbox import SubprocessSandbox

        assert resolve_sandbox_class("subprocess") is SubprocessSandbox

    def test_get_sandbox_registry(self):
        from praisonaiagents.sandbox._sandbox_bridge import get_sandbox_registry

        registry = get_sandbox_registry().default()
        assert "subprocess" in registry.list_names()

    def test_sandbox_install_hint(self):
        from praisonaiagents.sandbox._sandbox_bridge import sandbox_install_hint

        assert "docker" in sandbox_install_hint("docker").lower()


class TestSandboxCliRouting:
    def test_sandbox_typer_command_resolves(self):
        import click
        from praisonai_code.cli.app import app  # noqa: F401
        from typer.main import get_command as typer_get_command

        root = typer_get_command(app)
        ctx = click.Context(root)
        assert root.get_command(ctx, "sandbox") is not None

    def test_sandbox_run_and_backends_commands(self):
        from praisonai_code.cli.commands import sandbox as sandbox_mod

        assert hasattr(sandbox_mod, "sandbox_run")
        assert hasattr(sandbox_mod, "sandbox_backends")
