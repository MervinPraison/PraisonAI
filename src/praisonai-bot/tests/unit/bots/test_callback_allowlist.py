"""Button taps and slash commands pass the same allow-list as messages.

``is_sender_allowed`` is the silent form of the inbound pipeline's user and
channel checks. Every adapter callback that builds an ``InteractiveContext``,
and every registered slash command, must call it first. The guard test at the
bottom walks the adapter sources so a new callback handler cannot skip it.
"""

import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents.bots import BotConfig

BOTS_DIR = Path(__file__).resolve().parents[3] / "praisonai_bot" / "bots"


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))


def _cfg(**kw):
    return BotConfig(token="t", **kw)


def _adapter(config, paired=()):
    store = SimpleNamespace(is_paired=lambda uid, platform: uid in paired)
    return SimpleNamespace(config=config, _bot_context=SimpleNamespace(pairing_store=store), platform="x")


# ── the shared decision ────────────────────────────────────────────────────

def test_decision_matches_message_pipeline():
    from praisonai_bot.bots._unknown_user import is_sender_allowed

    cfg = _cfg(allowed_users=["U1"], allowed_channels=["C1"], owner_user_id="OWNER")
    adapter = _adapter(cfg, paired={"U2"})
    assert is_sender_allowed(adapter, "U1", "C1")
    assert is_sender_allowed(adapter, "U2", "C1")          # paired
    assert not is_sender_allowed(adapter, "EVE", "C1")     # unknown, policy deny
    assert not is_sender_allowed(adapter, "U1", "C9")      # channel not allowed
    assert not is_sender_allowed(adapter, "", "C1")
    assert is_sender_allowed(adapter, "OWNER", "DM-OWNER")  # pairing buttons in owner DM


def test_unknown_user_policy_allow_opens_callbacks():
    from praisonai_bot.bots._unknown_user import is_sender_allowed

    assert is_sender_allowed(_adapter(_cfg(unknown_user_policy="allow")), "anyone", "C1")
    # ``pair`` starts a pairing flow for messages; a tap never does.
    assert not is_sender_allowed(_adapter(_cfg(unknown_user_policy="pair")), "anyone", "C1")


# ── each adapter's callback path ───────────────────────────────────────────

def _registry():
    return SimpleNamespace(dispatch=AsyncMock(return_value=True))


@pytest.mark.parametrize("user, dispatched", [(1, True), (666, False)])
def test_telegram_callback_query(user, dispatched):
    from praisonai_bot.bots.telegram import TelegramBot

    bot = TelegramBot(token="123:abc", config=BotConfig(token="123:abc", allowed_users=["1"]))
    bot._interactive_registry = _registry()
    query = MagicMock(data="cmd:/approve abc allow")
    query.from_user.id = user
    query.message.chat_id = user
    query.answer = AsyncMock()
    asyncio.run(bot._handle_callback_query(SimpleNamespace(callback_query=query), None))
    assert bot._interactive_registry.dispatch.called is dispatched


@pytest.mark.parametrize("user, dispatched", [(1, True), (666, False)])
def test_discord_button_interaction(user, dispatched):
    from praisonai_bot.bots.discord import DiscordBot

    bot = DiscordBot(token="t", config=BotConfig(token="t", allowed_users=["1"]))
    bot._interactive_registry = _registry()
    interaction = MagicMock(channel_id=5)
    interaction.user.id = user
    interaction.response.defer = AsyncMock()
    asyncio.run(bot._handle_pairing_interaction(interaction, "cmd:/approve abc allow"))
    assert bot._interactive_registry.dispatch.called is dispatched


def _slack_handlers(monkeypatch, config):
    from praisonai_bot.bots.slack import SlackBot

    handlers = {}

    class _App:
        def __init__(self, *a, **k):
            pass

        def action(self, _pattern):
            def deco(fn):
                handlers["action"] = fn
                return fn
            return deco

        def command(self, name):
            def deco(fn):
                handlers[name] = fn
                return fn
            return deco

        def __getattr__(self, _name):
            return lambda *a, **k: (lambda fn: fn)

    client = MagicMock()
    client.auth_test = AsyncMock(return_value={"user_id": "UBOT", "user": "bot"})
    stubs = {
        "slack_bolt": MagicMock(),
        "slack_bolt.async_app": SimpleNamespace(AsyncApp=_App),
        "slack_bolt.adapter": MagicMock(),
        "slack_bolt.adapter.socket_mode": MagicMock(),
        "slack_bolt.adapter.socket_mode.async_handler": MagicMock(),
        "slack_sdk": MagicMock(),
        "slack_sdk.web": MagicMock(),
        "slack_sdk.web.async_client": SimpleNamespace(AsyncWebClient=lambda **k: client),
    }
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    bot = SlackBot(token="t", agent=MagicMock(), config=config)
    command = AsyncMock()
    bot._command_handlers = {"deploy": command}
    asyncio.run(bot.start())
    bot._interactive_registry = _registry()
    return bot, handlers, command


@pytest.mark.parametrize("user, dispatched", [("U1", True), ("EVE", False)])
def test_slack_block_action(monkeypatch, user, dispatched):
    bot, handlers, _ = _slack_handlers(monkeypatch, _cfg(allowed_users=["U1"]))
    body = {"user": {"id": user}, "channel": {"id": "C1"}, "message": {"ts": "1.0"}}
    asyncio.run(handlers["action"](AsyncMock(), body, {"value": "cmd:/approve abc allow"}))
    assert bot._interactive_registry.dispatch.called is dispatched


@pytest.mark.parametrize("user, ran", [("U1", True), ("EVE", False)])
def test_slack_slash_command(monkeypatch, user, ran):
    _, handlers, command = _slack_handlers(monkeypatch, _cfg(allowed_users=["U1"]))
    data = {"user_id": user, "channel_id": "C1", "text": "prod", "trigger_id": "t"}
    asyncio.run(handlers["/deploy"](AsyncMock(), data, AsyncMock()))
    assert command.called is ran


# ── guard: every callback handler in every adapter calls the shared check ──

def _is_callback_handler(fn):
    if any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("command", "action")
        for d in fn.decorator_list
    ):
        return True
    return any(
        isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "InteractiveContext"
        for n in ast.walk(fn)
    )


def test_every_adapter_callback_handler_checks_the_allow_list():
    handlers, unchecked = [], []
    for path in sorted(BOTS_DIR.glob("*.py")):
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_callback_handler(fn):
                name = f"{path.name}:{fn.name}"
                handlers.append(name)
                calls = {getattr(n.func, "id", None) for n in ast.walk(fn) if isinstance(n, ast.Call)}
                if "is_sender_allowed" not in calls:
                    unchecked.append(name)
    # Control: the walk must find the known handlers, or it proves nothing.
    assert {"telegram.py:_handle_callback_query", "slack.py:handle_block_actions",
            "slack.py:handle_command", "discord.py:_handle_pairing_interaction"} <= set(handlers)
    assert not unchecked, f"call is_sender_allowed() in: {unchecked}"


# ── privileged chat commands ──────────────────────────────────────────────

def test_undo_is_admin_only_once_a_policy_is_set():
    """/undo rolls back file changes on the host, like /learn it is privileged."""
    from praisonai_bot.bots._commands import CommandAccessPolicy

    policy = CommandAccessPolicy(admin_users={"admin-user"})
    assert not policy.can_run("regular-user", "undo")
    assert policy.can_run("admin-user", "undo")
    # No policy configured: unchanged, everyone may run it.
    assert CommandAccessPolicy().can_run("regular-user", "undo")
