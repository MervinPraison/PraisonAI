"""Core tests for the provider-quota-aware schedule hold (Issue #5386).

A recurring job whose model provider is rate-limited must stop re-firing and
re-failing every tick: the first 429 parks ``next`` due instant past the
provider's own reset window (``Retry-After``), intervening fires coalesce, and
the job becomes due again once the window elapses. Covers the pure decision
helper ``quota_hold_from_failure`` and the ``is_due`` hold guard, plus the
serialisation round-trip of the new ``hold_until`` field.
"""

from praisonaiagents.scheduler import quota_hold_from_failure
from praisonaiagents.scheduler.due import is_due
from praisonaiagents.scheduler.models import Schedule, ScheduleJob


class _RateLimited(Exception):
    """A 429-shaped provider error carrying a Retry-After header."""

    def __init__(self, retry_after):
        super().__init__("Rate limit exceeded")
        self.status_code = 429

        class _Resp:
            headers = {"retry-after": str(retry_after)}

        self.response = _Resp()


# ── quota_hold_from_failure (pure decision helper) ────────────────────


def test_rate_limit_with_retry_after_parks_past_window():
    now = 1000.0
    hold = quota_hold_from_failure(_RateLimited(3600), now, slack_seconds=60.0)
    assert hold == now + 3600 + 60


def test_retry_after_parsed_from_message_string():
    now = 500.0
    hold = quota_hold_from_failure(
        "429 Too Many Requests, retry after 30 seconds", now, slack_seconds=10.0
    )
    assert hold == now + 30 + 10


def test_retry_after_http_date_parks_past_window():
    # RFC 7231 allows Retry-After as an absolute HTTP-date, not just
    # delta-seconds. A provider that sends the reset instant as a date must
    # still park the job (greptile #2) — else a long quota window is ignored.
    import time
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    now = time.time()
    reset = format_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=1800)
    )
    hold = quota_hold_from_failure(_RateLimited(reset), now, slack_seconds=60.0)
    assert hold is not None
    # ~1800s window + 60s slack, allowing a little scheduling drift.
    assert now + 1800 + 60 - 5 <= hold <= now + 1800 + 60 + 5


def test_retry_after_past_http_date_does_not_hold():
    # An HTTP-date already in the past yields no usable window → no park.
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    past = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=120))
    assert quota_hold_from_failure(_RateLimited(past), 0.0) is None


def test_non_quota_failure_never_holds():
    assert quota_hold_from_failure(Exception("boom: invalid request"), 0.0) is None
    assert quota_hold_from_failure(Exception("connection reset"), 0.0) is None


def test_rate_limit_without_reset_hint_does_not_hold():
    # A 429 with no Retry-After / reset window carries no usable park instant.
    class _Bare(Exception):
        status_code = 429

    assert quota_hold_from_failure(_Bare("rate limited"), 0.0) is None


def test_slack_is_clamped_non_negative():
    now = 0.0
    assert quota_hold_from_failure(_RateLimited(100), now, slack_seconds=-5.0) == 100.0


def test_nan_retry_after_does_not_produce_nan_hold():
    # A 429 carrying a malformed ``nan`` Retry-After must not park the job with
    # a NaN hold instant (issue #5424) — it carries no usable window → no park.
    import math

    hold = quota_hold_from_failure(_RateLimited("nan"), 1000.0, slack_seconds=60.0)
    assert hold is None or math.isfinite(hold)
    assert hold is None


def test_negative_retry_after_does_not_hold():
    # A negative Retry-After is not a usable future window → no park.
    assert quota_hold_from_failure(_RateLimited(-30), 1000.0) is None


def test_echoed_negative_retry_after_in_message_does_not_hold():
    # A provider that echoes a negative Retry-After in the error message (e.g.
    # "retry after -3600 seconds") must not be read as a positive window that
    # parks the job on an invalid reset hint (issue #5424 / greptile #1).
    hold = quota_hold_from_failure(
        "429 Too Many Requests, retry after -3600 seconds", 1000.0, slack_seconds=60.0
    )
    assert hold is None


# ── is_due hold guard ─────────────────────────────────────────────────


def _every_job(**kw):
    return ScheduleJob(
        name="j", schedule=Schedule(kind="every", every_seconds=1), message="hi", **kw
    )


def test_held_job_not_due_within_window():
    job = _every_job(hold_until=2000.0)
    # Would otherwise be due (every-1s, never run) but is parked.
    assert is_due(job, now=1999.0) is False


def test_held_job_due_again_after_window():
    job = _every_job(hold_until=2000.0)
    assert is_due(job, now=2000.0) is True
    assert is_due(job, now=2500.0) is True


def test_unparked_job_unchanged():
    # No hold → today's behaviour exactly.
    assert is_due(_every_job(), now=123.0) is True


def test_intervening_fires_coalesce():
    # A parked every-1s job stays not-due across every intervening tick and
    # fires exactly once at the first legal instant after the window.
    job = _every_job(hold_until=100.0)
    assert [is_due(job, now=t) for t in (10, 50, 99)] == [False, False, False]
    assert is_due(job, now=100.0) is True


# ── serialisation round-trip ──────────────────────────────────────────


def test_hold_until_round_trips():
    job = _every_job(hold_until=4242.0)
    restored = ScheduleJob.from_dict(job.to_dict())
    assert restored.hold_until == 4242.0


def test_unparked_job_omits_hold_until_key():
    # A job that never hit a quota wall stays byte-for-byte unchanged.
    assert "hold_until" not in _every_job().to_dict()
