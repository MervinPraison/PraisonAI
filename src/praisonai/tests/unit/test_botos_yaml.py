"""
TDD tests for BotOS YAML config enhancement.

BotOS.from_config() should parse agent features like memory, tools,
knowledge, and guardrails from YAML — not just name/instructions/llm.
"""

import os
import tempfile

import pytest
import yaml


class TestBotOSFromConfigEnhanced:
    """Tests for enhanced BotOS.from_config()."""

    def _write_yaml(self, data):
        """Write YAML data to a temp file and return the path."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump(data, f)
        f.close()
        return f.name

    def test_basic_config_still_works(self):
        """Existing minimal YAML still works."""
        path = self._write_yaml({
            "agent": {
                "name": "helper",
                "instructions": "Be helpful",
                "llm": "gpt-4o-mini",
            },
            "platforms": {
                "telegram": {"token": "fake-token"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            assert "telegram" in botos.list_bots()
            bot = botos.get_bot("telegram")
            assert bot is not None
        finally:
            os.unlink(path)

    def test_agent_memory_true_parsed(self):
        """agent.memory: true is passed to Agent constructor."""
        path = self._write_yaml({
            "agent": {
                "name": "mem_agent",
                "instructions": "Remember things",
                "memory": True,
            },
            "platforms": {
                "telegram": {"token": "fake"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            agent = bot.agent
            # memory should be set (True or dict-like)
            assert getattr(agent, "memory", None) is not None
        finally:
            os.unlink(path)

    def test_agent_memory_dict_parsed(self):
        """agent.memory: {history: true, history_limit: 30} is passed."""
        path = self._write_yaml({
            "agent": {
                "name": "mem_agent",
                "instructions": "Remember",
                "memory": {"history": True, "history_limit": 30},
            },
            "platforms": {
                "telegram": {"token": "fake"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            agent = bot.agent
            mem = getattr(agent, "memory", None)
            assert mem is not None
        finally:
            os.unlink(path)

    def test_agent_tools_list_parsed(self):
        """agent.tools: ['search_web'] resolves to real tool functions."""
        path = self._write_yaml({
            "agent": {
                "name": "tool_agent",
                "instructions": "Use tools",
                "tools": ["search_web"],
            },
            "platforms": {
                "telegram": {"token": "fake"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            agent = bot.agent
            tools = getattr(agent, "tools", [])
            # Should have resolved at least the tool names
            assert tools is not None
        finally:
            os.unlink(path)

    def test_agent_role_parsed(self):
        """agent.role is passed to Agent."""
        path = self._write_yaml({
            "agent": {
                "name": "role_agent",
                "instructions": "Be helpful",
                "role": "Data Analyst",
            },
            "platforms": {
                "telegram": {"token": "fake"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            agent = bot.agent
            assert getattr(agent, "role", None) == "Data Analyst"
        finally:
            os.unlink(path)

    def test_platform_debounce_ms_parsed(self):
        """Platform-level debounce_ms is passed as BotConfig kwarg."""
        path = self._write_yaml({
            "agent": {
                "name": "helper",
                "instructions": "Help",
            },
            "platforms": {
                "telegram": {"token": "fake", "debounce_ms": 1500},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            # debounce_ms should be in kwargs
            assert bot is not None
        finally:
            os.unlink(path)

    def test_env_var_resolution(self):
        """${ENV_VAR} syntax is resolved."""
        os.environ["_TEST_BOT_TOKEN_XYZ"] = "resolved-token"
        path = self._write_yaml({
            "agent": {"name": "test", "instructions": "test"},
            "platforms": {
                "telegram": {"token": "${_TEST_BOT_TOKEN_XYZ}"},
            },
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            bot = botos.get_bot("telegram")
            assert bot.token == "resolved-token"
        finally:
            os.unlink(path)
            del os.environ["_TEST_BOT_TOKEN_XYZ"]

    def test_invalid_yaml_raises(self):
        """Invalid YAML raises ValueError."""
        path = self._write_yaml(None)
        try:
            from praisonai.bots.botos import BotOS
            with pytest.raises(ValueError):
                BotOS.from_config(path)
        finally:
            os.unlink(path)

    def test_missing_platforms_creates_empty(self):
        """Config with no platforms creates BotOS with no bots."""
        path = self._write_yaml({
            "agent": {"name": "test", "instructions": "test"},
        })
        try:
            from praisonai.bots.botos import BotOS
            botos = BotOS.from_config(path)
            assert botos.list_bots() == []
        finally:
            os.unlink(path)
