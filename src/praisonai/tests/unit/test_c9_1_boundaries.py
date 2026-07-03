"""C9.1 boundary tests — bot bridge and import gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_bot_bridge_import_module_requires_bot():
    from praisonai_code._bot_bridge import bot_package_available, import_bot_module

    if not bot_package_available():
        with pytest.raises(ImportError, match="pip install praisonai-bot"):
            import_bot_module("praisonai_bot.bots.bot")
    else:
        mod = import_bot_module("praisonai_bot.bots.bot")
        assert hasattr(mod, "Bot")


def test_c9_import_gate_script_passes():
    result = subprocess.run(
        ["bash", "scripts/check_c9_bot_imports.sh"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_audit_bot_wrapper_imports_passes():
    result = subprocess.run(
        ["bash", "scripts/audit_bot_wrapper_imports.sh"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sdk_gateway_lazy_resolves_bot_first():
    from praisonaiagents.gateway import WebSocketGateway

    assert WebSocketGateway is not None
    assert WebSocketGateway.__module__.startswith("praisonai_bot.")


def test_no_nested_praisonai_bot_under_wrapper():
    wrapper_pkg = REPO_ROOT / "src" / "praisonai" / "praisonai"
    assert not (wrapper_pkg / "praisonai_bot").exists()


def test_bot_registry_resolves_without_wrapper():
    """Built-in platform loaders must not require the praisonai wrapper."""
    from praisonai_bot.bots._registry import resolve_adapter

    telegram = resolve_adapter("telegram")
    assert telegram.__name__ == "TelegramBot"
    assert telegram.__module__.startswith("praisonai_bot.bots.")
