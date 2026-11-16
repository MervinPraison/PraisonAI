"""Issue #6138 — the core notification policy governs categorised proactive sends.

``praisonaiagents.push.policy.evaluate`` had no live consumer. These tests pin
that ``DeliveryRouter`` (configured from ``gateway.notifications``) now enforces
category opt-in, quiet hours and detail-level redaction, while leaving
uncategorised sends and unconfigured routers unchanged.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone

import pytest

from praisonai_bot.bots._notifications import NotificationGate, parse_preference
from praisonai_bot.bots.delivery import DeliveryRouter
from praisonaiagents.push.policy import DetailLevel, NotificationCategory


def _make_router(notifications=None):
    sent = []

    class FakeBot:
        async def send_message(self, channel_id, text):
            sent.append((channel_id, text))

    class FakeBotOS:
        def get_bot(self, platform):
            return FakeBot()

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS(), notifications=notifications)
    return router, sent


def _deliver(router, text, **kw):
    return asyncio.run(router.deliver("telegram:123", text, **kw))


def test_unconfigured_router_is_unchanged():
    router, sent = _make_router()
    assert _deliver(router, "secret result", category="agent_finished") is True
    assert sent == [("123", "secret result")]


def test_uncategorised_send_is_never_gated():
    router, sent = _make_router({"defaults": {"categories": []}})
    assert _deliver(router, "reply") is True
    assert sent == [("123", "reply")]


def test_unsubscribed_category_is_suppressed_without_retry():
    router, sent = _make_router(
        {"defaults": {"categories": ["approval_requested"]}}
    )
    # Reported as handled so schedulers/outbox do not retry a policy drop.
    assert _deliver(router, "done", category="agent_finished") is True
    assert sent == []


def test_detail_level_redacts_content_per_recipient():
    router, sent = _make_router({
        "defaults": {"categories": ["agent_finished"], "detail": "identified"},
        "recipients": {
            "telegram:999": {"detail": "detailed"},
        },
    })
    _deliver(router, "transcript tail", category="agent_finished",
             identity="cron_job1")
    asyncio.run(router.deliver("telegram:999", "transcript tail",
                               category="agent_finished"))
    assert sent == [("123", "Activity in cron_job1"), ("999", "transcript tail")]


@pytest.mark.parametrize(
    "utc_hour, expect_sent",
    [
        # 23:30 UTC = 08:30 Tokyo: outside Tokyo quiet hours (inside them in UTC).
        (23, True),
        # 13:30 UTC = 22:30 Tokyo: inside Tokyo quiet hours (outside them in UTC).
        (13, False),
    ],
)
def test_quiet_hours_use_recipient_timezone(monkeypatch, utc_hour, expect_sent):
    from praisonai_bot.bots import _notifications

    frozen = datetime(2026, 1, 15, utc_hour, 30, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    monkeypatch.setattr(_notifications, "datetime", FrozenDatetime)
    router, sent = _make_router({
        "recipients": {
            "telegram:123": {
                "categories": ["agent_finished"],
                "quiet_hours": "22:00-07:00",
                "timezone": "Asia/Tokyo",
                "detail": "detailed",
            },
        },
    })
    _deliver(router, "result", category="agent_finished")
    assert sent == ([("123", "result")] if expect_sent else [])


def test_set_notifications_replaces_and_clears_policy():
    router, sent = _make_router({"defaults": {"categories": []}})
    _deliver(router, "a", category="agent_finished")
    router.set_notifications(
        {"defaults": {"categories": ["agent_finished"], "detail": "detailed"}}
    )
    _deliver(router, "b", category="agent_finished")
    router.set_notifications(None)
    _deliver(router, "c", category="agent_finished")
    assert sent == [("123", "b"), ("123", "c")]


def test_parse_preference_inherits_and_validates():
    base = parse_preference({"detail": "private", "categories": ["agent_finished"]})
    pref = parse_preference({"quiet_hours": "22:00-07:30", "timezone": "Europe/London"}, base)
    assert pref.detail is DetailLevel.PRIVATE
    assert pref.categories == {NotificationCategory.AGENT_FINISHED}
    assert pref.quiet_hours == (time(22, 0), time(7, 30))
    with pytest.raises(ValueError):
        parse_preference({"categories": ["nope"]})
    with pytest.raises(ValueError):
        parse_preference({"detail": "loud"})
    with pytest.raises(ValueError):
        parse_preference({"timezone": "Europe/Londn"})


def test_gate_falls_back_to_defaults_for_unknown_recipient():
    gate = NotificationGate({"defaults": {"categories": ["agent_finished"]}})
    decision = gate.admit("slack:C1", "agent_finished", "x")
    assert decision.send is True
    assert gate.admit("slack:C1", "approval_requested", "x").send is False
