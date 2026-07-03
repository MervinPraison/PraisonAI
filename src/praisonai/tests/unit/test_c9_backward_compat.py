"""C9 backward-compat: praisonai.bots/gateway shims alias praisonai_bot."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BOT_PKG = REPO / "src" / "praisonai-bot"
WRAPPER_PKG = REPO / "src" / "praisonai"


@pytest.fixture(autouse=True)
def _bootstrap_paths():
    for p in (str(REPO / "src" / "praisonai-agents"), str(BOT_PKG), str(WRAPPER_PKG)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from praisonai._bootstrap import ensure_praisonai_bot, ensure_praisonai_code

    ensure_praisonai_bot()
    ensure_praisonai_code()
    yield


class TestBotModuleIdentity:
    @pytest.mark.parametrize(
        "old,new",
        [
            ("praisonai.bots.telegram", "praisonai_bot.bots.telegram"),
            ("praisonai.gateway.server", "praisonai_bot.gateway.server"),
            ("praisonai.bots.bot", "praisonai_bot.bots.bot"),
        ],
    )
    def test_module_identity(self, old: str, new: str):
        old_mod = importlib.import_module(old)
        new_mod = importlib.import_module(new)
        assert old_mod is new_mod

    def test_bot_class_identity(self):
        from praisonai.bots import Bot as OldBot
        from praisonai_bot.bots import Bot as NewBot

        assert OldBot is NewBot

    def test_no_nested_shadow_package(self):
        nested = WRAPPER_PKG / "praisonai" / "praisonai_bot"
        assert not nested.exists()

    def test_integration_gateway_host_shim(self):
        old_mod = importlib.import_module("praisonai.integration.gateway_host")
        new_mod = importlib.import_module("praisonai_bot.integration.gateway_host")
        assert old_mod is new_mod

    def test_scheduler_executor_shim(self):
        from praisonai.scheduler.executor import ScheduledAgentExecutor as ShimExec
        from praisonai_bot.scheduler.executor import ScheduledAgentExecutor as BotExec
        from praisonai.scheduler.condition_gate import ShellConditionGate as ShimGate
        from praisonai_bot.scheduler.condition_gate import ShellConditionGate as BotGate

        assert ShimExec is BotExec
        assert ShimGate is BotGate
