"""Wrapper emission seam for inbound platform events (Issue #5161).

``MessageHookMixin.fire_platform_event`` is the single DRY point every adapter
calls after translating a native SDK event (reaction/edit/delete/membership/
thread) into a core ``PlatformEvent``. These tests pin that it routes each
``PlatformEvent.kind`` to the matching ``HookEvent`` and fires it with the
normalised payload — and that it is a safe no-op when nothing is registered.
"""

import pytest

from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent, HookResult
from praisonaiagents.bots import PlatformEvent

from praisonai_bot.bots._protocol_mixin import MessageHookMixin


def _adapter_with_hook(event):
    """Build a minimal adapter whose registry has one hook on *event*."""
    reg = HookRegistry()
    seen = []
    reg.register_function(
        event=event,
        func=lambda d: (seen.append(d), HookResult.allow())[1],
    )

    class _Agent:
        agent_name = "bot"
        _hook_runner = HookRunner(reg)

    class _Adapter(MessageHookMixin):
        platform = "discord"

        def __init__(self):
            self._agent = _Agent()

    return _Adapter(), seen


@pytest.mark.parametrize("kind,event", [
    ("reaction_added", HookEvent.REACTION_RECEIVED),
    ("reaction_removed", HookEvent.REACTION_RECEIVED),
    ("message_edited", HookEvent.MESSAGE_EDITED),
    ("message_deleted", HookEvent.MESSAGE_DELETED),
    ("member_joined", HookEvent.MEMBER_JOINED),
    ("member_left", HookEvent.MEMBER_LEFT),
    ("thread_created", HookEvent.THREAD_CREATED),
])
def test_fire_platform_event_routes_kind_to_hook(kind, event):
    adapter, seen = _adapter_with_hook(event)
    adapter.fire_platform_event(
        PlatformEvent(kind=kind, platform="discord", chat_id="c1", user_id="u1")
    )
    assert len(seen) == 1, f"{kind} did not fire {event}"
    assert seen[0].kind == kind


def test_fire_platform_event_carries_reaction_emoji():
    adapter, seen = _adapter_with_hook(HookEvent.REACTION_RECEIVED)
    adapter.fire_platform_event(PlatformEvent(
        kind="reaction_added", platform="discord",
        chat_id="c1", user_id="u1", message_id="m1", emoji="✅",
    ))
    assert seen[0].emoji == "✅"
    assert seen[0].message_id == "m1"


def test_fire_platform_event_ignores_unknown_kind():
    adapter, seen = _adapter_with_hook(HookEvent.REACTION_RECEIVED)
    adapter.fire_platform_event(
        PlatformEvent(kind="bogus", platform="discord", chat_id="c1", user_id="u1")
    )
    assert seen == []


def test_fire_platform_event_is_noop_without_runner():
    class _Adapter(MessageHookMixin):
        platform = "discord"
        _agent = None

    # Must not raise when no hook runner is configured.
    _Adapter().fire_platform_event(
        PlatformEvent(kind="reaction_added", platform="discord", chat_id="c", user_id="u")
    )


# --- Discord adapter handler wiring (Issue #5161) ----------------------------

class _FakeClient:
    """Minimal stand-in for a discord.py client used to capture handlers."""

    def __init__(self, bot_id="999"):
        self.user = type("U", (), {"id": bot_id})()
        self.handlers = {}

    def event(self, coro):
        self.handlers[coro.__name__] = coro
        return coro


def _discord_bot_with_reactions():
    """Build a DiscordBot with only the reaction handlers registered."""
    from praisonai_bot.bots.discord import DiscordBot

    bot = DiscordBot(token="x")
    fired = []
    bot.fire_platform_event = lambda evt: fired.append(evt)  # type: ignore
    bot._client = _FakeClient()
    bot._register_platform_event_handlers({"reactions"})
    return bot, fired


class _RawReaction:
    def __init__(self, user_id, channel_id="c1", message_id="m1", emoji="✅"):
        self.user_id = user_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.emoji = emoji


@pytest.mark.asyncio
async def test_discord_reaction_remove_ignores_bot_own_removal():
    # A bot's own ack/done cleanup removal must NOT surface as an inbound event.
    bot, fired = _discord_bot_with_reactions()
    handler = bot._client.handlers["on_raw_reaction_remove"]
    await handler(_RawReaction(user_id="999"))  # 999 == bot user id
    assert fired == []


@pytest.mark.asyncio
async def test_discord_reaction_remove_surfaces_user_removal():
    bot, fired = _discord_bot_with_reactions()
    handler = bot._client.handlers["on_raw_reaction_remove"]
    await handler(_RawReaction(user_id="42"))
    assert len(fired) == 1
    assert fired[0].kind == "reaction_removed"
    assert fired[0].user_id == "42"


@pytest.mark.asyncio
async def test_discord_reaction_add_ignores_bot_own_reaction():
    bot, fired = _discord_bot_with_reactions()
    handler = bot._client.handlers["on_raw_reaction_add"]
    await handler(_RawReaction(user_id="999"))
    assert fired == []


def test_discord_event_classes_read_from_metadata():
    from praisonaiagents.bots import BotConfig
    from praisonai_bot.bots.discord import DiscordBot

    cfg = BotConfig(token="x")
    cfg.metadata["events"] = ["reactions", "edits"]
    bot = DiscordBot(token="x", config=cfg)
    assert bot._event_classes() == {"reactions", "edits"}
