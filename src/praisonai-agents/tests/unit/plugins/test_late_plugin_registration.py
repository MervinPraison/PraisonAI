"""Late plugin registration must honour a selective plugins.enable() allow-list."""

from unittest.mock import patch

import pytest

from praisonaiagents import Agent
from praisonaiagents.plugins.manager import get_plugin_manager
from praisonaiagents.plugins.plugin import Plugin, PluginInfo


def _allowed_tool() -> str:
    """Tool from the allow-listed plugin."""
    return "allowed"


def _late_tool() -> str:
    """Tool from a plugin registered after selective enable."""
    return "late"


def _tool_plugin(name: str, tool):
    class _Plugin(Plugin):
        @property
        def info(self):
            return PluginInfo(name=name)

        def get_tools(self):
            return [tool]

    return _Plugin()


@pytest.fixture
def plugin_state_reset():
    """Reset global plugin facade state after each test."""
    from praisonaiagents import plugins

    saved_enabled = plugins._plugins_enabled
    saved_names = plugins._enabled_plugin_names
    yield
    plugins._plugins_enabled = saved_enabled
    plugins._enabled_plugin_names = saved_names


def test_late_registered_plugin_respects_selective_allow_list(plugin_state_reset):
    """After plugins.enable([...]), a newly registered plugin stays disabled."""
    from praisonaiagents import plugins

    manager = get_plugin_manager()
    allowed = _tool_plugin("only_this", _allowed_tool)
    late = _tool_plugin("late_plugin", _late_tool)

    try:
        with patch.object(manager, "auto_discover_plugins", return_value=0), patch.object(
            manager, "discover_entry_points", return_value=0
        ):
            assert manager.register(allowed)
            plugins.enable(["only_this"])

            assert manager.is_enabled("only_this") is True
            assert manager.register(late)
            assert manager.is_enabled("late_plugin") is False
            assert len(manager.get_all_tools()) == 1

            agent = Agent(instructions="test", llm="gpt-4o-mini")
            tool_names = [
                getattr(t, "__name__", getattr(t, "name", str(t))) for t in agent.tools
            ]
            assert "_allowed_tool" in tool_names
            assert "_late_tool" not in tool_names
    finally:
        manager.unregister("late_plugin")
        manager.unregister("only_this")
        plugins.disable()
