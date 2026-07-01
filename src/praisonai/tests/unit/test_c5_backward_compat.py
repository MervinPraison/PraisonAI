"""Backward-compatibility gate for praisonai-code C5 extraction.

Verifies old ``praisonai.*`` import paths, module identity for patching,
CLI entry points, and bot-layer modules that must remain in the wrapper.
"""

from __future__ import annotations

import importlib
import inspect
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_LEGACY_PYTHONPATH = os.pathsep.join(
    [
        str(REPO_ROOT / "src" / "praisonai-agents"),
        str(REPO_ROOT / "src" / "praisonai"),
    ]
)


def _legacy_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = _LEGACY_PYTHONPATH
    return env


def _run_legacy_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "praisonai.cli.main", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
        env=_legacy_env(),
    )


def _run_typer_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "praisonai", *args],
        capture_output=True,
        text=True,
        timeout=25,
        cwd=str(REPO_ROOT),
        env=_legacy_env(),
    )


def _run_runtime_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "praisonai.runtime", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
        env=_legacy_env(),
    )


class TestImportPathAliases:
    """Old import paths must resolve to the same module objects as praisonai_code."""

    @pytest.mark.parametrize(
        "old_path,new_path",
        [
            ("praisonai.cli.main", "praisonai_code.cli.main"),
            ("praisonai.cli.app", "praisonai_code.cli.app"),
            ("praisonai.cli.commands.run", "praisonai_code.cli.commands.run"),
            ("praisonai.cli.commands.doctor", "praisonai_code.cli.commands.doctor"),
            ("praisonai.cli.output.console", "praisonai_code.cli.output.console"),
            ("praisonai.cli.configuration.resolver", "praisonai_code.cli.configuration.resolver"),
            ("praisonai.cli.unified_schema", "praisonai_code.cli.unified_schema"),
            ("praisonai.cli.schema_provider", "praisonai_code.cli.schema_provider"),
            ("praisonai.cli.fallback_schema", "praisonai_code.cli.fallback_schema"),
            ("praisonai.cli._warnings", "praisonai_code.cli._warnings"),
            ("praisonai.runtime.descriptor", "praisonai_code.runtime.descriptor"),
            ("praisonai.cli_backends.registry", "praisonai_code.cli_backends.registry"),
            ("praisonai.llm.env", "praisonai_code.llm.env"),
            ("praisonai.llm.credentials", "praisonai_code.llm.credentials"),
            ("praisonai.llm.catalogue", "praisonai_code.llm.catalogue"),
            ("praisonai.llm.config", "praisonai_code.llm.config"),
            ("praisonai._framework_availability", "praisonai_code._framework_availability"),
            ("praisonai._safe_loader", "praisonai_code._safe_loader"),
            ("praisonai.tool_resolver", "praisonai_code.tool_resolver"),
            ("praisonai.tool_registry", "praisonai_code.tool_registry"),
        ],
    )
    def test_module_identity(self, old_path: str, new_path: str):
        old_mod = importlib.import_module(old_path)
        new_mod = importlib.import_module(new_path)
        assert old_mod is new_mod, f"{old_path} and {new_path} must be the same module object"

    def test_praisonai_class_importable_from_old_path(self):
        from praisonai.cli.main import PraisonAI as OldPraisonAI
        from praisonai_code.cli.main import PraisonAI as NewPraisonAI

        assert OldPraisonAI is NewPraisonAI

    def test_feature_handler_lazy_import(self):
        from praisonai.cli.features import MCPHandler

        from praisonai_code.cli.features.mcp import MCPHandler as CodeMCPHandler

        assert MCPHandler is CodeMCPHandler

    def test_config_schema_at_legacy_path(self):
        import praisonai.cli.configuration as configuration

        schema_path = Path(configuration.__file__).parent / "config.schema.json"
        assert schema_path.exists()


class TestPatchTargetCompatibility:
    """unittest.mock.patch on old dotted paths must hit moved implementation."""

    def test_patch_run_module(self):
        with patch("praisonai.cli.commands.run.app") as mocked:
            import praisonai.cli.commands.run as run_mod

            run_mod.app  # noqa: B018 — trigger attribute access
            mocked  # patched object registered

    def test_patch_main_praisonai(self):
        with patch("praisonai.cli.main.PraisonAI") as mocked:
            from praisonai.cli.main import PraisonAI

            assert PraisonAI is mocked


class TestCliEntryPoints:
    def test_python_m_praisonai_cli_main_help(self):
        result = _run_legacy_cli("--help")
        assert result.returncode == 0
        assert "--cli-backend" in result.stdout

    def test_praisonai_main_import(self):
        from praisonai.__main__ import main

        assert callable(main)

    @pytest.mark.parametrize("command,marker", [("gateway", "Gateway"), ("bot", "bot")])
    def test_typer_wrapper_commands_help(self, command: str, marker: str):
        result = _run_typer_cli(command, "--help")
        assert result.returncode == 0, result.stderr
        assert marker.lower() in (result.stdout + result.stderr).lower()

    def test_python_m_praisonai_runtime_help(self):
        result = _run_runtime_cli("--help")
        assert result.returncode == 0
        assert "--host" in result.stdout or "host" in result.stdout.lower()

    def test_bootstrap_resolves_praisonai_code_on_legacy_pythonpath(self):
        script = (
            "import praisonai; "
            "from praisonai.cli.unified_schema import rag_schema_provider; "
            "import praisonai_code; "
            "assert rag_schema_provider is not None; "
            "print(praisonai_code.__version__)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(REPO_ROOT),
            env=_legacy_env(),
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip()


class TestBotLayerUnchanged:
    """Bot/channel modules must remain real wrapper implementations, not shims."""

    @pytest.mark.parametrize(
        "module_path,marker",
        [
            ("praisonai.cli.commands.gateway", "Manage the PraisonAI Gateway"),
            ("praisonai.cli.commands.bot", "messaging bots"),
            ("praisonai.cli.features.gateway", "gateway"),
            ("praisonai.cli.features.bots_cli", "BotHandler"),
        ],
    )
    def test_bot_modules_are_wrapper_local(self, module_path: str, marker: str):
        mod = importlib.import_module(module_path)
        source = inspect.getsourcefile(mod) or ""
        assert "/praisonai/praisonai/" in source.replace("\\", "/")
        assert "praisonai-code" not in source.replace("\\", "/")
        assert marker.lower() in inspect.getsource(mod).lower() or hasattr(mod, marker)

    def test_no_nested_praisonai_code_package(self):
        nested = REPO_ROOT / "src" / "praisonai" / "praisonai_code"
        assert not nested.exists(), "nested praisonai_code must not shadow praisonai-code package"
