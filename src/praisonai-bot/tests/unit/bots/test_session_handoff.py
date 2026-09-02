#!/usr/bin/env python3
"""Tests for gateway live-session handoff (Issue #4660).

``BotOS.handoff`` re-homes an in-progress conversation onto a freshly created
thread/DM on another platform: it creates the destination thread via the
existing ``DeliveryRouter.create_thread`` primitive, seeds that thread's
session with the origin transcript, optionally posts a seed message and drops a
breadcrumb in the origin — routing subsequent turns to the new channel.
"""

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.bots import BotOS, ThreadRef  # noqa: E402


class _FakeSession:
    """Minimal BotSessionManager stand-in for handoff export/seed."""

    def __init__(self, histories=None):
        self._by_key = dict(histories or {})
        self.seeded = {}

    def export_history(self, storage_key):
        return list(self._by_key.get(storage_key, []))

    def seed_history(self, storage_key, history):
        self.seeded[storage_key] = list(history)


class _FakeAdapter:
    """Adapter exposing the native thread primitive + capability flag."""

    def __init__(self, *, threads=True, thread_id="T-99"):
        self.capabilities = {"threads": threads}
        self._thread_id = thread_id
        self.created = []

    async def create_thread(self, channel_id, name):
        self.created.append((channel_id, name))
        return self._thread_id


class _FakeBot:
    """Channel bot stub: platform + adapter + session manager + home channel."""

    def __init__(self, platform, *, adapter, session, home="C-home"):
        self.platform = platform
        self.adapter = adapter
        self._session = session
        self._home_channel = home
        self.sends = []

    async def send_message(self, channel_id, text, thread_id=None):
        self.sends.append((channel_id, text, thread_id))
        return {"ok": True}


def _make_botos(bot):
    botos = BotOS(bots=[])
    botos._bots[bot.platform] = bot
    # Point the router's home channel so a bare "<platform>" target resolves.
    botos.delivery_router.directory.set_home_channel(bot.platform, bot._home_channel)
    return botos


def test_handoff_creates_thread_and_seeds_session():
    transcript = [
        {"role": "user", "content": "start on laptop"},
        {"role": "assistant", "content": "working..."},
    ]
    session = _FakeSession({"cli:alice": transcript})
    adapter = _FakeAdapter(threads=True, thread_id="T-42")
    bot = _FakeBot("telegram", adapter=adapter, session=session)
    botos = _make_botos(bot)

    ref = asyncio.run(botos.handoff("cli:alice", "telegram"))

    assert isinstance(ref, ThreadRef)
    assert ref.ok
    assert ref.platform == "telegram"
    assert ref.thread_id == "T-42"
    assert ref.session_key == "telegram:C-home:T-42"
    assert ref.target == "telegram:C-home:T-42"
    # Thread was created and the origin transcript was seeded onto it.
    assert adapter.created == [("C-home", "Handoff")]
    assert session.seeded["telegram:C-home:T-42"] == transcript


def test_handoff_posts_seed_text_into_new_thread():
    session = _FakeSession({"cli:alice": [{"role": "user", "content": "hi"}]})
    adapter = _FakeAdapter(thread_id="T-7")
    bot = _FakeBot("telegram", adapter=adapter, session=session)
    botos = _make_botos(bot)

    ref = asyncio.run(
        botos.handoff("cli:alice", "telegram", seed_text="Continuing here")
    )

    assert ref.ok
    # The seed message was delivered to the new thread.
    assert any(
        text == "Continuing here" and thread == "T-7"
        for (_chan, text, thread) in bot.sends
    )


def test_handoff_unsupported_when_adapter_cannot_thread():
    session = _FakeSession({"cli:alice": [{"role": "user", "content": "hi"}]})
    adapter = _FakeAdapter(threads=False)
    bot = _FakeBot("telegram", adapter=adapter, session=session)
    botos = _make_botos(bot)

    ref = asyncio.run(botos.handoff("cli:alice", "telegram"))

    assert not ref.ok
    assert ref.status == "unsupported"
    # No session was seeded for a handoff that could not create a thread.
    assert session.seeded == {}


def test_handoff_no_route_for_unknown_platform():
    session = _FakeSession({"cli:alice": [{"role": "user", "content": "hi"}]})
    adapter = _FakeAdapter()
    bot = _FakeBot("telegram", adapter=adapter, session=session)
    botos = _make_botos(bot)

    ref = asyncio.run(botos.handoff("cli:alice", "whatsapp"))

    assert not ref.ok
    assert ref.status in ("no_route", "unsupported")
    assert session.seeded == {}


def test_handoff_of_empty_session_still_creates_thread():
    session = _FakeSession({})  # no transcript for this key
    adapter = _FakeAdapter(thread_id="T-1")
    bot = _FakeBot("telegram", adapter=adapter, session=session)
    botos = _make_botos(bot)

    ref = asyncio.run(botos.handoff("cli:ghost", "telegram"))

    assert ref.ok
    assert adapter.created == [("C-home", "Handoff")]
    # Nothing to seed, but the thread was still opened cleanly.
    assert session.seeded == {}


if __name__ == "__main__":
    test_handoff_creates_thread_and_seeds_session()
    test_handoff_posts_seed_text_into_new_thread()
    test_handoff_unsupported_when_adapter_cannot_thread()
    test_handoff_no_route_for_unknown_platform()
    test_handoff_of_empty_session_still_creates_thread()
    print("all handoff tests passed")
