"""Regression test for Signal inbound idle-stall detection (Issue #4289).

A silently half-open Signal transport keeps returning a successfully-empty
``[]`` from the bridge without ever raising. If an empty poll refreshed the
inbound-liveness timestamp, ``health.last_activity`` would stay fresh forever
and the shared ``evaluate_channel_health`` STALE_SOCKET seam could never flag a
"deaf" channel. These tests pin that only a *delivered* envelope advances
inbound liveness, so a stalled poll loop remains detectable.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonai_bot.bots.signal import SignalBot


class _FakeResponse:
    def __init__(self, payload):
        self.status = 200
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload


def _bot_with_response(payload):
    bot = SignalBot(account="+15551234567")
    session = MagicMock()
    session.get = MagicMock(return_value=_FakeResponse(payload))
    bot._http_session = session
    return bot


@pytest.mark.asyncio
async def test_empty_poll_does_not_refresh_inbound_liveness():
    bot = _bot_with_response([])
    bot._last_inbound_activity = None

    await bot._poll_once()

    assert getattr(bot, "_last_inbound_activity", None) is None


@pytest.mark.asyncio
async def test_delivered_envelope_refreshes_inbound_liveness():
    envelope = {"envelope": {"source": "+15550001111", "dataMessage": {"message": "hi"}}}
    bot = _bot_with_response([envelope])
    bot._last_inbound_activity = None

    before = time.time()
    await bot._poll_once()

    assert bot._last_inbound_activity is not None
    assert bot._last_inbound_activity >= before
