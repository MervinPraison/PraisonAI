"""Issue #2537 — completed background job delivery routing.

Exercises ``BotOS.on_background_job_complete`` / ``_deliver_job_text`` against a
real ``DeliveryRouter`` over a fake BotOS, verifying the reviewer-flagged
behaviours: the ``deliver="all"`` broadcast token fans out to every home
channel and a threaded origin preserves its ``thread_id``.
"""

from __future__ import annotations

from types import SimpleNamespace

from praisonai_bot.bots.botos import BotOS
from praisonai_bot.bots.delivery import DeliveryRouter


def _make_router(homes):
    """Build a DeliveryRouter over a fake BotOS recording every send."""
    sent = []

    class FakeBot:
        def __init__(self, platform):
            self._platform = platform

        async def send_message(self, channel_id, text):
            sent.append((self._platform, channel_id, text))

    bots = {p: FakeBot(p) for p in homes}

    class FakeBotOS:
        def get_bot(self, platform):
            return bots.get(platform)

        def list_bots(self):
            return list(bots)

    router = DeliveryRouter(FakeBotOS())
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    for platform, channel in homes.items():
        router.directory.set_home_channel(platform, channel)
    return router, sent


def _bind_botos(router):
    """Minimal object exposing the delivery methods under test."""
    os_like = SimpleNamespace(_delivery_router=router)
    os_like.on_background_job_complete = (
        BotOS.on_background_job_complete.__get__(os_like, BotOS)
    )
    os_like._deliver_job_text = BotOS._deliver_job_text.__get__(os_like, BotOS)
    os_like._summarize_job_result = BotOS._summarize_job_result
    os_like._run_coroutine_sync = BotOS._run_coroutine_sync
    os_like._get_hook_runner = lambda: None
    return os_like


def _job(
    deliver,
    platform="telegram",
    chat_id="123",
    thread_id="",
    session_id="",
    result=None,
):
    return SimpleNamespace(
        job_id="j1",
        status=SimpleNamespace(value="completed"),
        error=None,
        result=result if result is not None else {"success": True, "output": "hi"},
        origin={
            "deliver": deliver,
            "platform": platform,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "session_id": session_id,
        },
    )


def test_deliver_all_fans_out_to_every_home_channel():
    router, sent = _make_router({"telegram": "111", "slack": "222"})
    os_like = _bind_botos(router)

    delivered = os_like.on_background_job_complete(_job(deliver="all"))

    assert delivered is True
    platforms = sorted(s[0] for s in sent)
    assert platforms == ["slack", "telegram"]
    assert all(s[2] == "hi" for s in sent)


def test_deliver_origin_delivers_to_origin_channel():
    router, sent = _make_router({"telegram": "111"})
    os_like = _bind_botos(router)

    delivered = os_like.on_background_job_complete(
        _job(deliver="origin", chat_id="123", thread_id="t-9")
    )

    assert delivered is True
    assert sent == [("telegram", "123", "hi")]


def test_no_deliver_target_is_pull_only():
    router, sent = _make_router({"telegram": "111"})
    os_like = _bind_botos(router)

    delivered = os_like.on_background_job_complete(_job(deliver=""))

    assert delivered is False
    assert sent == []


def test_job_completed_hook_receives_origin_session_id():
    """The JOB_COMPLETED hook must carry the originating session_id (#2537)."""
    router, _sent = _make_router({"telegram": "111"})
    os_like = _bind_botos(router)

    captured = {}

    class FakeRunner:
        def execute_sync(self, event, event_input):
            captured["session_id"] = getattr(event_input, "session_id", None)
            captured["thread_id"] = getattr(event_input, "thread_id", None)

    os_like._get_hook_runner = lambda: FakeRunner()

    os_like.on_background_job_complete(
        _job(deliver="origin", session_id="sess-42", thread_id="t-9")
    )

    assert captured.get("session_id") == "sess-42"
    assert captured.get("thread_id") == "t-9"
