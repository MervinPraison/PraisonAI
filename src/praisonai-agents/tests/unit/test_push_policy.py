"""Tests for the pure notification policy in praisonaiagents.push.policy."""

from datetime import datetime, time, timezone, timedelta

import pytest

from praisonaiagents.push import (
    DEFAULT_PREFERENCE,
    DetailLevel,
    NotificationCategory,
    NotificationDecision,
    NotificationPreference,
    evaluate,
)


class TestExports:
    def test_symbols_importable_from_push(self):
        assert NotificationCategory.APPROVAL_REQUESTED.value == "approval_requested"
        assert DetailLevel.PRIVATE.value == "private"
        assert isinstance(DEFAULT_PREFERENCE, NotificationPreference)


class TestCategoryFilter:
    def test_unsubscribed_category_suppressed(self):
        prefs = NotificationPreference(categories={NotificationCategory.AGENT_FINISHED})
        decision = evaluate(NotificationCategory.AGENT_QUESTION, prefs)
        assert decision.send is False
        assert decision.reason == "category_not_subscribed"
        assert decision.redacted_content is None

    def test_subscribed_category_sent(self):
        prefs = NotificationPreference(categories={NotificationCategory.AGENT_FINISHED})
        decision = evaluate(
            NotificationCategory.AGENT_FINISHED, prefs, content="transcript"
        )
        assert decision.send is True
        assert decision.reason == "ok"

    def test_default_preference_used_when_none(self):
        # DEFAULT_PREFERENCE opts into approval + question, not agent_finished.
        assert evaluate(NotificationCategory.APPROVAL_REQUESTED).send is True
        assert evaluate(NotificationCategory.AGENT_FINISHED).send is False


class TestDetailLevelRedaction:
    def _prefs(self, detail):
        return NotificationPreference(
            categories={NotificationCategory.AGENT_FINISHED}, detail=detail
        )

    def test_private_hides_everything(self):
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(DetailLevel.PRIVATE),
            content="secret transcript",
            identity="session-42",
        )
        assert d.redacted_content == "You have new activity"

    def test_identified_shows_identity_not_content(self):
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(DetailLevel.IDENTIFIED),
            content="secret transcript",
            identity="session-42",
        )
        assert d.redacted_content == "Activity in session-42"
        assert "secret" not in d.redacted_content

    def test_detailed_includes_content(self):
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(DetailLevel.DETAILED),
            content="full transcript tail",
            identity="session-42",
        )
        assert d.redacted_content == "full transcript tail"

    def test_identified_without_identity_falls_back(self):
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(DetailLevel.IDENTIFIED),
            content="x",
        )
        assert d.redacted_content == "You have new activity"


class TestQuietHours:
    def _prefs(self, **kw):
        base = dict(
            categories={NotificationCategory.AGENT_FINISHED,
                        NotificationCategory.APPROVAL_REQUESTED},
            quiet_hours=(time(22, 0), time(7, 30)),
            timezone="UTC",
        )
        base.update(kw)
        return NotificationPreference(**base)

    def test_suppressed_inside_wrapping_window(self):
        now = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
        d = evaluate(NotificationCategory.AGENT_FINISHED, self._prefs(), now=now)
        assert d.send is False
        assert d.reason == "quiet_hours"

    def test_suppressed_after_midnight_before_end(self):
        now = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
        d = evaluate(NotificationCategory.AGENT_FINISHED, self._prefs(), now=now)
        assert d.send is False

    def test_sent_outside_window(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        d = evaluate(NotificationCategory.AGENT_FINISHED, self._prefs(), now=now)
        assert d.send is True

    def test_urgent_overrides_quiet_hours(self):
        now = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
        d = evaluate(
            NotificationCategory.APPROVAL_REQUESTED,
            self._prefs(),
            now=now,
            is_urgent=True,
        )
        assert d.send is True
        assert d.reason == "urgent_override"

    def test_urgent_does_not_override_when_disabled(self):
        now = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
        d = evaluate(
            NotificationCategory.APPROVAL_REQUESTED,
            self._prefs(urgent_overrides_quiet=False),
            now=now,
            is_urgent=True,
        )
        assert d.send is False
        assert d.reason == "quiet_hours"

    def test_timezone_applied(self):
        # 23:00 UTC is 08:00 in Asia/Tokyo (+09:00) — outside the quiet window.
        now = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(timezone="Asia/Tokyo"),
            now=now,
        )
        assert d.send is True

    def test_no_quiet_hours_always_considered(self):
        prefs = NotificationPreference(
            categories={NotificationCategory.AGENT_FINISHED}
        )
        now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
        assert evaluate(NotificationCategory.AGENT_FINISHED, prefs, now=now).send


    def test_unknown_timezone_falls_back_to_utc(self):
        # A bad IANA name must not leave the aware ``now`` on its original clock;
        # it falls back to UTC so quiet hours stay deterministic. 23:00 UTC is
        # inside the 22:00-07:30 window, so this is suppressed.
        now = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
        d = evaluate(
            NotificationCategory.AGENT_FINISHED,
            self._prefs(timezone="Not/AZone"),
            now=now,
        )
        assert d.send is False
        assert d.reason == "quiet_hours"

    def test_default_now_uses_recipient_timezone_not_host(self):
        # With now omitted, the recipient's zone must drive the decision rather
        # than the host clock. Build a window that is always "now" in Tokyo so
        # the result is independent of where the test runs.
        tokyo_now = datetime.now(timezone(timedelta(hours=9)))
        start = (tokyo_now - timedelta(hours=1)).time()
        end = (tokyo_now + timedelta(hours=1)).time()
        prefs = NotificationPreference(
            categories={NotificationCategory.AGENT_FINISHED},
            quiet_hours=(start, end),
            timezone="Asia/Tokyo",
        )
        assert evaluate(NotificationCategory.AGENT_FINISHED, prefs).send is False


class TestDefaultPreferenceIsolation:
    def test_mutating_active_prefs_does_not_leak_into_default(self):
        before = set(DEFAULT_PREFERENCE.categories)
        # Evaluate with default prefs, then a separate caller mutating their own
        # copy must never change the shared DEFAULT_PREFERENCE.
        evaluate(NotificationCategory.APPROVAL_REQUESTED)
        rogue = NotificationPreference(categories=set(DEFAULT_PREFERENCE.categories))
        rogue.categories.add(NotificationCategory.AGENT_FINISHED)
        assert DEFAULT_PREFERENCE.categories == before
        assert NotificationCategory.AGENT_FINISHED not in DEFAULT_PREFERENCE.categories


class TestPreferenceHelpers:
    def test_allows(self):
        prefs = NotificationPreference(categories={NotificationCategory.AGENT_QUESTION})
        assert prefs.allows(NotificationCategory.AGENT_QUESTION)
        assert not prefs.allows(NotificationCategory.AGENT_FINISHED)
