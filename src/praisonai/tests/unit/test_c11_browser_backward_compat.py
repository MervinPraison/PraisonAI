"""C11 backward-compat: praisonai.browser shims alias praisonai_browser."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BROWSER_PKG = REPO / "src" / "praisonai-browser"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (
        str(REPO / "src" / "praisonai-agents"),
        str(BROWSER_PKG),
        str(WRAPPER_PKG),
        str(REPO / "src" / "praisonai-code"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_browser, ensure_praisonai_code

    ensure_praisonai_browser()
    ensure_praisonai_code()
    yield


class TestBrowserModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.browser.server", "praisonai_browser.server"),
            ("praisonai.browser.agent", "praisonai_browser.agent"),
            ("praisonai.browser.sessions", "praisonai_browser.sessions"),
            ("praisonai.browser.cdp_agent", "praisonai_browser.cdp_agent"),
            ("praisonai.browser.protocol", "praisonai_browser.protocol"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_browser_server_class_identity(self):
        from praisonai.browser import BrowserServer as OldServer
        from praisonai_browser import BrowserServer as NewServer

        assert OldServer is NewServer

    def test_cli_shim_app_identity(self):
        from praisonai.browser.cli.app import app as old_app
        from praisonai_browser.cli.commands.browser import app as new_app

        assert old_app is new_app

    def test_command_shim_identity(self):
        old_mod = importlib.import_module("praisonai.cli.commands.browser")
        new_mod = importlib.import_module("praisonai_browser.cli.commands.browser")
        assert old_mod is new_mod

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_browser"
        assert not nested.exists()


class TestBrowserLazyImports:
    @pytest.mark.parametrize("module", ["praisonai_browser", "praisonai_browser.server"])
    def test_import_pulls_no_server_deps(self, module: str):
        heavy = ("fastapi", "uvicorn", "playwright")
        already = {name for name in heavy if name in sys.modules}
        importlib.import_module(module)
        pulled = [name for name in heavy if name in sys.modules and name not in already]
        assert not pulled, f"{module} eagerly imported heavy deps: {pulled}"

    def test_top_level_lazy_exports(self):
        import praisonai_browser

        assert hasattr(praisonai_browser, "__version__")
        server_cls = praisonai_browser.BrowserServer
        assert server_cls.__name__ == "BrowserServer"


class TestBrowserCliRouting:
    def test_browser_resident_commands_declared(self):
        from praisonai_code.cli import app as code_app

        assert "browser" in code_app._BROWSER_RESIDENT_COMMANDS
        assert "browser" not in code_app._WRAPPER_RESIDENT_COMMANDS

    def test_browser_bridge_available(self):
        from praisonai_code._browser_bridge import browser_package_available

        assert browser_package_available() is True

    def test_get_command_resolves_browser(self):
        import click
        from praisonai_code.cli.app import app  # noqa: F401
        from typer.main import get_command as typer_get_command

        root = typer_get_command(app)
        ctx = click.Context(root)
        cmd = root.get_command(ctx, "browser")
        assert cmd is not None

    def test_browser_tool_stays_in_code_tier(self):
        from praisonai_code.cli.commands import browser_tool

        assert hasattr(browser_tool, "app")
