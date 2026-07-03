#!/usr/bin/env python3
"""Tests for gateway readiness (/ready) and liveness (/live) probe helpers."""

import asyncio
import sys
from pathlib import Path

# Resolve from the repository root so direct execution finds the packages.
REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway
from praisonai_bot.gateway.supervisor import ChannelState, ChannelStatus


def _make_gateway():
    return WebSocketGateway()


def test_readiness_startup_pending_before_start():
    """Not started yet -> readiness reports startup-pending and is not ready."""
    gw = _make_gateway()
    failing = asyncio.run(gw._readiness_failures())
    assert "startup-pending" in failing
    assert failing  # not ready


def test_readiness_ready_when_running():
    """Running and not draining -> ready (no failures)."""
    gw = _make_gateway()
    gw._is_running = True
    gw._draining = False
    failing = asyncio.run(gw._readiness_failures())
    assert failing == []


def test_readiness_draining_flag():
    """Draining -> readiness reports draining and is not ready."""
    gw = _make_gateway()
    gw._is_running = True
    gw._draining = True
    failing = asyncio.run(gw._readiness_failures())
    assert "draining" in failing


def test_readiness_failed_channel():
    """A FAILED channel surfaces as channel:<name> in readiness failures."""
    gw = _make_gateway()
    gw._is_running = True
    gw._draining = False
    gw._channel_supervisor._channels["telegram"] = ChannelStatus(
        state=ChannelState.FAILED
    )
    failing = asyncio.run(gw._readiness_failures())
    assert "channel:telegram" in failing


def test_paused_channel_does_not_block_readiness():
    """A PAUSED channel does not block readiness."""
    gw = _make_gateway()
    gw._is_running = True
    gw._draining = False
    gw._channel_supervisor._channels["slack"] = ChannelStatus(
        state=ChannelState.PAUSED
    )
    failing = asyncio.run(gw._readiness_failures())
    assert failing == []


def test_event_loop_responsive_true():
    """A free event loop is reported responsive."""
    gw = _make_gateway()
    assert asyncio.run(gw._event_loop_responsive()) is True


def test_unhealthy_channels_lists_failed_only():
    gw = _make_gateway()
    gw._channel_supervisor._channels["a"] = ChannelStatus(state=ChannelState.FAILED)
    gw._channel_supervisor._channels["b"] = ChannelStatus(state=ChannelState.RUNNING)
    names = [n for n, _ in gw._unhealthy_channels()]
    assert names == ["a"]


def test_draining_does_not_report_startup_pending():
    """After shutdown, readiness reports only draining, not startup-pending."""
    gw = _make_gateway()
    gw._draining = True
    gw._is_running = False
    failing = asyncio.run(gw._readiness_failures())
    assert "draining" in failing
    assert "startup-pending" not in failing


def test_draining_reset_clears_ready_after_restart():
    """Re-running start()'s reset on a stopped instance clears the draining flag."""
    gw = _make_gateway()
    gw._is_running = False
    gw._draining = True
    # Emulate the reset performed at the top of start().
    gw._draining = False
    gw._is_running = True
    failing = asyncio.run(gw._readiness_failures())
    assert failing == []


if __name__ == "__main__":
    test_readiness_startup_pending_before_start()
    test_readiness_ready_when_running()
    test_readiness_draining_flag()
    test_readiness_failed_channel()
    test_paused_channel_does_not_block_readiness()
    test_event_loop_responsive_true()
    test_unhealthy_channels_lists_failed_only()
    test_draining_does_not_report_startup_pending()
    test_draining_reset_clears_ready_after_restart()
    print("All readiness/liveness tests passed")
