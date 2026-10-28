"""Telemetry shutdown must return promptly when the PostHog flush is wedged."""

import threading
import time
from unittest.mock import MagicMock

from praisonaiagents.telemetry.telemetry import MinimalTelemetry


class _FastJoinThread(threading.Thread):
    def join(self, timeout=None):
        return super().join(timeout=0.2 if timeout else timeout)


def test_shutdown_returns_when_flush_hangs(monkeypatch):
    release = threading.Event()
    client = MagicMock()
    client.flush.side_effect = lambda: release.wait(10)

    telemetry = MinimalTelemetry(enabled=False)
    telemetry.enabled = True
    telemetry._shutdown_lock = threading.Lock()
    telemetry._shutdown_complete = False
    telemetry._posthog = client
    monkeypatch.setattr(telemetry, "flush", lambda: None)
    monkeypatch.setattr(threading, "Thread", _FastJoinThread)

    start = time.monotonic()
    try:
        telemetry.shutdown()
    finally:
        release.set()
    assert time.monotonic() - start < 2
    # Cleanup that would block on the same wedged transport is skipped.
    client.shutdown.assert_not_called()
    assert telemetry._posthog is None
