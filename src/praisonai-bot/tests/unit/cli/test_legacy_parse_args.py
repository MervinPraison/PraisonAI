"""Tests for C8.4 legacy parse_args decomposition."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
_LEGACY_PYTHONPATH = os.pathsep.join(
    [
        str(REPO_ROOT / "src" / "praisonai-agents"),
        str(REPO_ROOT / "src" / "praisonai"),
        str(REPO_ROOT / "src" / "praisonai-code"),
    ]
)


def _legacy_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONPATH"] = _LEGACY_PYTHONPATH
    return env


class TestMainPyLineCount:
    def test_main_py_within_limit(self):
        from pathlib import Path

        main_py = (
            REPO_ROOT
            / "src"
            / "praisonai-code"
            / "praisonai_code"
            / "cli"
            / "main.py"
        )
        lines = main_py.read_text().count("\n") + 1
        assert lines <= 300, f"main.py has {lines} lines (max 300)"


class TestLegacyModuleImports:
    def test_praison_ai_importable_from_main(self):
        from praisonai_code.cli.main import PraisonAI

        assert PraisonAI is not None
        assert callable(PraisonAI)

    def test_env_security_reexported(self):
        from praisonai_code.cli.main import _validate_env_key

        with pytest.raises(ValueError, match="not allowed"):
            _validate_env_key("LD_PRELOAD")

    def test_wrapper_legacy_modules_importable(self):
        from praisonai.cli.legacy import subcommand_handlers
        from praisonai_bot.cli.legacy.dispatch import argparse_builder, legacy_dispatch

        assert hasattr(subcommand_handlers, "handle_memory_command")
        assert hasattr(argparse_builder, "build_argument_parser")
        assert hasattr(legacy_dispatch, "run_wrapper_feature")


class TestDeadBranchRemoval:
    def test_no_duplicate_serve_in_special_commands_block(self):
        """Dead serve branch (features.serve) must not exist in praison_ai."""
        from pathlib import Path

        text = (
            REPO_ROOT
            / "src"
            / "praisonai-code"
            / "praisonai_code"
            / "cli"
            / "legacy"
            / "praison_ai.py"
        ).read_text()
        # Old dead pattern: elif serve -> features.serve handle_serve_command
        assert "from .features.serve import handle_serve_command" not in text


class TestDelegateMethodsOnClass:
    """P0: delegates must be on PraisonAI, not inside if __name__."""

    @pytest.mark.parametrize(
        "method",
        [
            "handle_direct_prompt",
            "handle_memory_command",
            "handle_workflow_command",
            "_start_interactive_mode",
            "_load_interactive_tools",
            "_load_tools",
        ],
    )
    def test_praison_ai_has_delegate(self, method):
        from praisonai_code.cli.main import PraisonAI

        assert hasattr(PraisonAI, method), f"PraisonAI missing {method}"
        assert callable(getattr(PraisonAI, method))


class TestFeatureImportPaths:
    """Legacy parse_args feature branches must use ..features not .features."""

    def test_praison_ai_no_single_dot_features(self):
        text = (
            REPO_ROOT
            / "src"
            / "praisonai-code"
            / "praisonai_code"
            / "cli"
            / "legacy"
            / "praison_ai.py"
        ).read_text()
        assert "from .features." not in text
        assert "from ..features." in text


class TestLegacyDispatch:
    def test_gateway_dispatch_without_wrapper(self):
        from praisonai_bot.cli.legacy.dispatch.legacy_dispatch import dispatch_gateway
        from praisonai_code.cli.main import PraisonAI
        import argparse

        args = argparse.Namespace(model=None)
        with patch("praisonai_code._wrapper_bridge.wrapper_available", return_value=False):
            code = dispatch_gateway(PraisonAI(), args, ["start"])
        assert code == 1

    def test_parse_args_help_subprocess(self):
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.main", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
            env=_legacy_env(),
        )
        assert result.returncode == 0
        combined = (result.stdout + result.stderr).lower()
        assert "usage" in combined or "praisonai" in combined
