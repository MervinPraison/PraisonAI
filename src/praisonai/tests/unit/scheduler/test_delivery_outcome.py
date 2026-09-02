"""Unit tests for truthful scheduled-delivery outcome accounting (Issue #4454).

Covers the typed :class:`DeliveryOutcome` classification and the shared
``_finalize_delivery`` accounting so a scheduled run that fails to deliver its
result to the configured chat target fires ``on_failure`` (and is counted)
instead of being silently reported as ``on_success``.
"""

import warnings
from unittest.mock import AsyncMock, Mock

import pytest

from praisonai.scheduler._base_scheduler import DeliveryOutcome

with warnings.catch_warnings():
    warnings.simplefilter("ignore", PendingDeprecationWarning)
    from praisonai.scheduler.agent_scheduler import AgentScheduler
    from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sync_scheduler(deliver="", **kwargs):
    agent = Mock()
    agent.start = Mock(return_value="result")
    return AgentScheduler(agent, "task", deliver=deliver, **kwargs)


def _async_scheduler(deliver="", **kwargs):
    agent = Mock()
    agent.astart = AsyncMock(return_value="result")
    return AsyncAgentScheduler(agent, "task", deliver=deliver, **kwargs)


class _FakeDelivery:
    """Stub delivery wrapper whose ``deliver`` returns a fixed bool or raises."""

    def __init__(self, *, ok=True, raises=False):
        self._ok = ok
        self._raises = raises

    def deliver(self, text):
        if self._raises:
            raise RuntimeError("send failed")
        return self._ok


# ---------------------------------------------------------------------------
# DeliveryOutcome classification (_deliver_result)
# ---------------------------------------------------------------------------

class TestDeliverResultOutcome:
    def test_not_configured(self):
        sched = _sync_scheduler(deliver="")
        assert sched._deliver_result("hello") is DeliveryOutcome.NOT_CONFIGURED

    def test_suppressed_intentional_silence(self):
        sched = _sync_scheduler(deliver="telegram:1")
        assert sched._deliver_result("NO_REPLY") is DeliveryOutcome.SUPPRESSED

    def test_delivered(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(ok=True)
        assert sched._deliver_result("hi") is DeliveryOutcome.DELIVERED

    def test_undelivered_when_router_returns_false(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(ok=False)
        assert sched._deliver_result("hi") is DeliveryOutcome.UNDELIVERED

    def test_undelivered_when_delivery_raises(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(raises=True)
        assert sched._deliver_result("hi") is DeliveryOutcome.UNDELIVERED

    def test_undelivered_when_wrapper_unbuildable(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = None
        sched._build_delivery = lambda: None  # simulate a build failure
        assert sched._deliver_result("hi") is DeliveryOutcome.UNDELIVERED


# ---------------------------------------------------------------------------
# _finalize_delivery accounting
# ---------------------------------------------------------------------------

class TestFinalizeDeliveryAccounting:
    def test_delivered_counts_and_returns_true(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(ok=True)
        assert sched._finalize_delivery("hi") is True
        assert sched._delivered_count == 1
        assert sched._undelivered_count == 0

    def test_undelivered_counts_and_returns_false(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(ok=False)
        assert sched._finalize_delivery("hi") is False
        assert sched._delivered_count == 0
        assert sched._undelivered_count == 1

    def test_suppressed_is_success_without_counting(self):
        sched = _sync_scheduler(deliver="telegram:1")
        assert sched._finalize_delivery("NO_REPLY") is True
        assert sched._delivered_count == 0
        assert sched._undelivered_count == 0

    def test_not_configured_is_success_without_counting(self):
        sched = _sync_scheduler(deliver="")
        assert sched._finalize_delivery("hi") is True
        assert sched._delivered_count == 0
        assert sched._undelivered_count == 0

    def test_stats_exposes_delivery_counters(self):
        sched = _sync_scheduler(deliver="telegram:1")
        sched._delivery = _FakeDelivery(ok=True)
        sched._finalize_delivery("hi")
        stats = sched.get_stats()
        assert stats["delivered_deliveries"] == 1
        assert stats["undelivered_deliveries"] == 0


# ---------------------------------------------------------------------------
# Sync scheduler execute_once folds delivery outcome into callbacks
# ---------------------------------------------------------------------------

class TestSyncExecuteOnceOutcome:
    def test_execute_once_undelivered_fires_on_failure(self):
        on_success = Mock()
        on_failure = Mock()
        sched = _sync_scheduler(
            deliver="telegram:1", on_success=on_success, on_failure=on_failure
        )
        sched._delivery = _FakeDelivery(ok=False)
        sched.execute_once()
        on_failure.assert_called_once()
        on_success.assert_not_called()
        assert sched._undelivered_count == 1

    def test_execute_once_delivered_fires_on_success(self):
        on_success = Mock()
        on_failure = Mock()
        sched = _sync_scheduler(
            deliver="telegram:1", on_success=on_success, on_failure=on_failure
        )
        sched._delivery = _FakeDelivery(ok=True)
        sched.execute_once()
        on_success.assert_called_once()
        on_failure.assert_not_called()
        assert sched._delivered_count == 1


# ---------------------------------------------------------------------------
# Async scheduler execute_once folds delivery outcome into callbacks
# ---------------------------------------------------------------------------

class TestAsyncExecuteOnceOutcome:
    @pytest.mark.asyncio
    async def test_execute_once_undelivered_fires_on_failure(self):
        on_success = Mock()
        on_failure = Mock()
        sched = _async_scheduler(
            deliver="telegram:1", on_success=on_success, on_failure=on_failure
        )
        sched._delivery = _FakeDelivery(ok=False)
        await sched.execute_once()
        on_failure.assert_called_once()
        on_success.assert_not_called()
        assert sched._undelivered_count == 1

    @pytest.mark.asyncio
    async def test_execute_once_delivered_fires_on_success(self):
        on_success = Mock()
        on_failure = Mock()
        sched = _async_scheduler(
            deliver="telegram:1", on_success=on_success, on_failure=on_failure
        )
        sched._delivery = _FakeDelivery(ok=True)
        await sched.execute_once()
        on_success.assert_called_once()
        on_failure.assert_not_called()
        assert sched._delivered_count == 1
