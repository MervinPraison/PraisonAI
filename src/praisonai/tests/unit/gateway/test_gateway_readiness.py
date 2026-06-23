#!/usr/bin/env python3
"""Tests for gateway readiness (/ready) and liveness (/live) probe helpers."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonai.gateway.server import WebSocketGateway
from praisonai.gateway.supervisor import ChannelState, ChannelStatus


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


if __name__ == "__main__":
    test_readiness_startup_pending_before_start()
    test_readiness_ready_when_running()
    test_readiness_draining_flag()
    test_readiness_failed_channel()
    test_paused_channel_does_not_block_readiness()
    test_event_loop_responsive_true()
    test_unhealthy_channels_lists_failed_only()
    print("All readiness/liveness tests passed")
