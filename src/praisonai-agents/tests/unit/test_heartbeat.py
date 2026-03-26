"""Tests for Heartbeat Agent (F2).

Tests the standalone Heartbeat class that runs agents on a schedule.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestHeartbeatImports:
    """Test lazy imports work correctly."""

    def test_import_from_agent_module(self):
        from praisonaiagents.agent import Heartbeat
        assert Heartbeat is not None

    def test_import_from_package(self):
        from praisonaiagents import Heartbeat
        assert Heartbeat is not None

    def test_import_config(self):
        from praisonaiagents import HeartbeatConfig
        assert HeartbeatConfig is not None

    def test_import_config_from_agent(self):
        from praisonaiagents.agent import HeartbeatConfig
        assert HeartbeatConfig is not None


class TestHeartbeatConfig:
    """Test HeartbeatConfig dataclass."""

    def test_defaults(self):
        from praisonaiagents.agent.heartbeat import HeartbeatConfig
        cfg = HeartbeatConfig()
        assert cfg.schedule == "hourly"
        assert cfg.prompt is None
        assert cfg.on_result is None
        assert cfg.on_error == "retry"
        assert cfg.max_retries == 3

    def test_custom_values(self):
        from praisonaiagents.agent.heartbeat import HeartbeatConfig
        cb = lambda x: x
        cfg = HeartbeatConfig(schedule="daily", prompt="check", on_result=cb, max_retries=5)
        assert cfg.schedule == "daily"
        assert cfg.prompt == "check"
        assert cfg.on_result is cb
        assert cfg.max_retries == 5


class TestHeartbeatInit:
    """Test Heartbeat initialization."""

    def test_creates_with_agent(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        agent = MagicMock(name="test_agent")
        hb = Heartbeat(agent, schedule="hourly")
        assert hb.agent is agent
        assert hb.config.schedule == "hourly"
        assert hb._running is False

    def test_hourly_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="hourly")
        assert hb._interval_seconds == 3600.0

    def test_daily_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="daily")
        assert hb._interval_seconds == 86400.0

    def test_weekly_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="weekly")
        assert hb._interval_seconds == 604800.0

    def test_every_30m_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="every 30m")
        assert hb._interval_seconds == 1800.0

    def test_every_6h_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="every 6h")
        assert hb._interval_seconds == 21600.0

    def test_every_10s_interval(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="every 10s")
        assert hb._interval_seconds == 10.0


class TestHeartbeatStartStop:
    """Test start/stop lifecycle."""

    def test_start_nonblocking(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        agent = MagicMock()
        agent.start.side_effect = Exception("stop")
        hb = Heartbeat(agent, schedule="hourly", max_retries=1)
        hb.start(blocking=False)
        assert hb._running is True
        hb.stop()
        assert hb._running is False

    def test_stop_sets_flag(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="hourly")
        hb._running = True
        hb.stop()
        assert not hb.is_running

    def test_is_running_property(self):
        from praisonaiagents.agent.heartbeat import Heartbeat
        hb = Heartbeat(MagicMock(), schedule="hourly")
        assert not hb.is_running
        hb._running = True
        assert hb.is_running


class TestHeartbeatDoesNotModifyAgent:
    """Verify Heartbeat is truly standalone."""

    def test_agent_class_unchanged(self):
        """Agent class should have no heartbeat-related attributes."""
        from praisonaiagents import Agent
        agent = Agent(name="test", instructions="test")
        assert not hasattr(agent, '_heartbeat')
        assert not hasattr(agent, 'heartbeat')
