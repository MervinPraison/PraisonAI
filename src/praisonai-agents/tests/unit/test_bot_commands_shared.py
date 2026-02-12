"""Unit tests for shared bot command utilities (_commands.py)."""

import time
import sys
import os

# Add wrapper to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai'))


class MockAgent:
    """Minimal mock of Agent."""

    def __init__(self, name="test-agent", llm="gpt-4o-mini"):
        self.name = name
        self.llm = llm


class TestFormatStatus:
    """Test format_status utility."""

    def test_import(self):
        from praisonai.bots._commands import format_status
        assert format_status is not None

    def test_basic_status(self):
        from praisonai.bots._commands import format_status
        agent = MockAgent()
        result = format_status(agent, "telegram", time.time() - 60, True)
        assert "test-agent" in result
        assert "gpt-4o-mini" in result
        assert "telegram" in result
        assert "True" in result
        assert "0h 1m" in result

    def test_no_agent(self):
        from praisonai.bots._commands import format_status
        result = format_status(None, "discord", None, False)
        assert "No agent" in result
        assert "discord" in result
        assert "False" in result

    def test_no_started_at(self):
        from praisonai.bots._commands import format_status
        agent = MockAgent()
        result = format_status(agent, "slack", None, True)
        assert "Uptime: \n" in result or "Uptime: " in result

    def test_all_platforms(self):
        from praisonai.bots._commands import format_status
        agent = MockAgent()
        for platform in ["telegram", "discord", "slack"]:
            result = format_status(agent, platform, time.time(), True)
            assert platform in result


class TestFormatHelp:
    """Test format_help utility."""

    def test_import(self):
        from praisonai.bots._commands import format_help
        assert format_help is not None

    def test_basic_help(self):
        from praisonai.bots._commands import format_help
        agent = MockAgent()
        result = format_help(agent, "telegram")
        assert "/status" in result
        assert "/new" in result
        assert "/help" in result
        assert "test-agent" in result
        assert "gpt-4o-mini" in result

    def test_help_with_extra_commands(self):
        from praisonai.bots._commands import format_help
        agent = MockAgent()
        result = format_help(agent, "discord", {"stats": "Show statistics"})
        assert "/stats - Show statistics" in result

    def test_help_no_agent(self):
        from praisonai.bots._commands import format_help
        result = format_help(None, "slack")
        assert "No agent" in result

    def test_help_no_extra_commands(self):
        from praisonai.bots._commands import format_help
        agent = MockAgent()
        result = format_help(agent, "telegram", None)
        assert "/status" in result

    def test_help_empty_extra(self):
        from praisonai.bots._commands import format_help
        agent = MockAgent()
        result = format_help(agent, "telegram", {})
        lines = result.strip().split("\n")
        # Should have: header, /status, /new, /help, blank, Agent, Model
        assert len(lines) >= 6


class TestDRYConsistency:
    """Verify all platforms produce identical format from the shared utility."""

    def test_same_output_all_platforms(self):
        from praisonai.bots._commands import format_status, format_help
        agent = MockAgent()
        started = time.time() - 3661  # 1h 1m 1s

        statuses = {}
        helps = {}
        for platform in ["telegram", "discord", "slack"]:
            s = format_status(agent, platform, started, True)
            h = format_help(agent, platform, {"test": "Test cmd"})
            # Replace platform name to check structural equality
            statuses[platform] = s.replace(platform, "PLATFORM")
            helps[platform] = h.replace(platform, "PLATFORM")

        # All should be structurally identical
        assert statuses["telegram"] == statuses["discord"] == statuses["slack"]
        assert helps["telegram"] == helps["discord"] == helps["slack"]
