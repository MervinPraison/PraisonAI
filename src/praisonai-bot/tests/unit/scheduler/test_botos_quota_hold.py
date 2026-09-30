"""BotOS schedule-loop provider-quota hold (Issue #5386, greptile #1).

The BotOS ``_run_schedule_loop`` runs ``agent.chat`` directly rather than
through :class:`ScheduledAgentExecutor`, so it needs the same provider-quota
hold or a 429/quota failure re-fires every tick against a benched provider.
These tests cover the pure ``_apply_schedule_quota_hold`` decision the loop
applies before ``mark_run``: a 429 with a reset hint parks the job, a
non-quota failure never parks, a later hold is never shortened, and a success
clears a prior park.
"""

import time

import pytest

try:
    from praisonai_bot.bots.botos import BotOS
except ImportError:  # pragma: no cover - optional deps not installed
    BotOS = None

pytestmark = pytest.mark.skipif(BotOS is None, reason="praisonai bots not importable")


class _Job:
    def __init__(self):
        self.name = "j"
        self.hold_until = None


class _RateLimited(Exception):
    """A 429-shaped provider error carrying a Retry-After header."""

    def __init__(self, retry_after):
        super().__init__("Rate limit exceeded")
        self.status_code = 429

        class _Resp:
            headers = {"retry-after": str(retry_after)}

        self.response = _Resp()


def test_rate_limit_failure_parks_botos_job():
    job = _Job()
    now = time.time()
    BotOS._apply_schedule_quota_hold(
        job, succeeded=False, error=_RateLimited(3600),
    )
    assert job.hold_until is not None
    # Parked past the ~3600s window (+ default 60s slack), allowing drift.
    assert now + 3600 <= job.hold_until <= now + 3600 + 120


def test_non_quota_failure_does_not_park():
    job = _Job()
    BotOS._apply_schedule_quota_hold(
        job, succeeded=False, error=Exception("boom: invalid request"),
    )
    assert job.hold_until is None


def test_never_shortens_an_existing_later_hold():
    job = _Job()
    job.hold_until = time.time() + 10_000
    prior = job.hold_until
    BotOS._apply_schedule_quota_hold(
        job, succeeded=False, error=_RateLimited(60),
    )
    # A shorter new window must not shorten a job already parked further out.
    assert job.hold_until == prior


def test_success_clears_prior_hold():
    job = _Job()
    job.hold_until = time.time() + 3600
    BotOS._apply_schedule_quota_hold(job, succeeded=True, error=None)
    assert job.hold_until is None


def test_failure_without_exception_is_inert():
    job = _Job()
    BotOS._apply_schedule_quota_hold(job, succeeded=False, error=None)
    assert job.hold_until is None
