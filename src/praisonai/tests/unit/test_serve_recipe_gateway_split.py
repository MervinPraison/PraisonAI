"""C9.6b — serve recipe gateway split boundary tests."""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
BOT_PKG = REPO / "src" / "praisonai-bot"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _paths():
    for p in (str(REPO / "src" / "praisonai-agents"), str(BOT_PKG), str(WRAPPER_PKG)):
        if p not in sys.path:
            sys.path.insert(0, p)
    yield


def test_recipe_gateway_lives_in_bot_package():
    from praisonai_bot.cli.features import recipe_gateway

    assert hasattr(recipe_gateway, "run_recipe_gateway")
    src = inspect.getsourcefile(recipe_gateway.run_recipe_gateway)
    assert src is not None
    assert "praisonai-bot" in src.replace("\\", "/")


def test_wrapper_serve_recipe_delegates_to_bot():
    from praisonai._bootstrap import ensure_praisonai_bot

    ensure_praisonai_bot()
    from praisonai.cli.features.serve import ServeHandler

    source = inspect.getsource(ServeHandler.cmd_recipe)
    assert "recipe_gateway" in source
    assert "from praisonai.gateway import WebSocketGateway" not in source
    assert "from praisonai_bot.cli.features.recipe_gateway import run_recipe_gateway" in source


def test_recipe_gateway_validation_without_name():
    from praisonai_bot.cli.features.recipe_gateway import run_recipe_gateway

    assert run_recipe_gateway(host="127.0.0.1", port=8765, recipe_name="") == 2
