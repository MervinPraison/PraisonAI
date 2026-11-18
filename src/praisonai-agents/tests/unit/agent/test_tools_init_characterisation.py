"""Pin the tools/toolsets block of ``Agent.__init__`` before it moves (T-05).

Characterisation tests: they record what a caller observes today after
``Agent(...)`` (tools normalisation, ``toolsets=``, autonomy default tools,
plugin-tool merge, tool output limit) so the block can be moved into a
``config/agent_init.py`` resolver without changing behaviour.
"""

import logging
import sys

import pytest

import praisonaiagents.plugins as plugins_mod
import praisonaiagents.plugins.manager as manager_mod
import praisonaiagents.toolsets as toolsets_mod
from praisonaiagents import Agent
from praisonaiagents.agent.autonomy import AutonomyConfig
from praisonaiagents.config.feature_configs import OutputConfig, ToolConfig
from praisonaiagents.config.loader import clear_config_cache
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginInfo
from praisonaiagents.tools.resolver import ToolResolutionError


def my_tool(x: str) -> str:
    """Caller tool."""
    return x


def plugin_tool(x: str) -> str:
    """Tool contributed by a plugin."""
    return x


def plugin_my_tool(x: str) -> str:
    """Plugin tool whose name collides with the caller's ``my_tool``."""
    return x


plugin_my_tool.__name__ = "my_tool"


def names(tools):
    return [getattr(t, "__name__", None) or getattr(t, "name", None) for t in tools]


def make(**kwargs):
    return Agent(instructions="hi", model="gpt-4o-mini", **kwargs)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("PRAISONAI_STRICT_TOOLS", raising=False)
    # A developer's ~/.praisonai/config.toml (global or via the upward cwd walk)
    # can enable plugins; plugin auto-enable also runs once per process.
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    clear_config_cache()
    monkeypatch.setattr(plugins_mod, "_auto_enable_attempted", False)
    monkeypatch.setattr(plugins_mod, "_plugins_enabled", False)
    monkeypatch.setattr(plugins_mod, "_enabled_plugin_names", None)
    monkeypatch.setattr(manager_mod, "_default_manager", None)
    monkeypatch.setattr(toolsets_mod, "_global_registry", toolsets_mod.ToolsetRegistry())
    yield
    clear_config_cache()


class _ToolPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="char_tools")

    def get_tools(self):
        return [plugin_tool, plugin_my_tool]


@pytest.fixture
def tool_plugin(monkeypatch):
    """Register a PluginType.TOOL plugin on a fresh global manager."""
    manager = PluginManager()
    monkeypatch.setattr(manager_mod, "_default_manager", manager)
    assert manager.register(_ToolPlugin())
    return manager


# --- tools= normalisation ---------------------------------------------------

def test_no_tools_is_empty_list():
    assert make().tools == []


def test_single_callable_is_wrapped_in_list():
    assert make(tools=my_tool).tools == [my_tool]


def test_single_name_string_is_resolved():
    tools = make(tools="read_file").tools
    assert isinstance(tools, list) and names(tools) == ["read_file"]


def test_tuple_is_resolved_per_element_into_new_list():
    agent = make(tools=(my_tool, "read_file"))
    assert isinstance(agent.tools, list)
    assert names(agent.tools) == ["my_tool", "read_file"]
    assert agent.tools[0] is my_tool


def test_list_is_copied_and_caller_list_not_mutated():
    caller = [my_tool]
    agent = make(tools=caller, toolsets=["safe"])
    assert agent.tools is not caller
    assert caller == [my_tool]
    assert agent.tools[0] is my_tool


def test_other_tools_object_is_kept_as_is():
    spec = {"type": "web_search"}
    assert make(tools=spec).tools is spec


def test_unknown_name_is_dropped_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="praisonaiagents.tools.resolver"):
        agent = make(tools=[my_tool, "nope_tool"])
    assert agent.tools == [my_tool]
    assert "Unknown tool 'nope_tool'" in caplog.text


def test_unknown_name_raises_in_strict_mode(monkeypatch):
    monkeypatch.setenv("PRAISONAI_STRICT_TOOLS", "1")
    with pytest.raises(ToolResolutionError) as exc:
        make(tools=["nope_tool"])
    assert exc.value.unknown == ["nope_tool"]


# --- toolsets= ----------------------------------------------------------------

def test_toolsets_appended_after_tools_without_duplicates():
    agent = make(tools=[my_tool, "read_file"], toolsets=["safe"])
    assert names(agent.tools) == ["my_tool", "read_file", "internet_search", "tavily_search"]


@pytest.mark.parametrize("model, first, second", [
    ("gpt-4o-mini", "edit_file", "apply_patch"),
    ("claude-sonnet-4-5", "apply_patch", "edit_file"),
])
def test_toolsets_order_edit_primitive_by_model(model, first, second):
    tools = names(Agent(instructions="hi", model=model, toolsets=["coding"]).tools)
    assert tools[1:3] == [first, second]


def test_unknown_toolset_raises_wrapped_value_error():
    with pytest.raises(ValueError, match=r"failed to resolve toolsets \['nope'\]") as exc:
        make(toolsets=["nope"])
    assert type(exc.value) is ValueError
    assert "list_toolsets()" in str(exc.value)


def test_toolset_strict_unknown_tool_keeps_typed_error(monkeypatch):
    toolsets_mod.register_toolset("char_bad", tools=["nope_tool"])
    monkeypatch.setenv("PRAISONAI_STRICT_TOOLS", "1")
    with pytest.raises(ToolResolutionError) as exc:
        make(toolsets=["char_bad"])
    assert exc.value.unknown == ["nope_tool"]


def test_toolsets_module_import_failure_current_behaviour(monkeypatch):
    # Pinned as-is: the import fails before ToolResolutionError is bound, so the
    # ``except ToolResolutionError`` clause raises UnboundLocalError and the
    # ImportError wrapper below it is unreachable. Update if the move fixes it.
    monkeypatch.setitem(sys.modules, "praisonaiagents.toolsets", None)
    with pytest.raises(UnboundLocalError, match="ToolResolutionError"):
        make(toolsets=["safe"])


# --- autonomy default tools -----------------------------------------------------

def test_autonomy_injects_profile_tools_when_no_tools_given():
    from praisonaiagents import tools as tools_module
    from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
    expected = names(getattr(tools_module, n) for n in AUTONOMY_PROFILE.tools)
    assert names(make(autonomy=True).tools) == expected


def test_autonomy_skips_profile_tools_that_do_not_exist(monkeypatch):
    from praisonaiagents.tools.profiles import AUTONOMY_PROFILE
    monkeypatch.setattr(AUTONOMY_PROFILE, "tools", ["read_file", "no_such_tool_xyz"])
    assert names(make(autonomy=True).tools) == ["read_file"]


def test_autonomy_falls_back_to_ast_grep_without_profiles(monkeypatch):
    monkeypatch.setitem(sys.modules, "praisonaiagents.tools.profiles", None)
    assert names(make(autonomy=True).tools) == [
        "ast_grep_search", "ast_grep_rewrite", "ast_grep_scan"]


@pytest.mark.parametrize("kwargs", [{"tools": [my_tool]}, {"toolsets": ["safe"]}])
def test_autonomy_injects_nothing_when_caller_gave_tools(kwargs):
    agent = make(autonomy=True, **kwargs)
    assert "ast_grep_search" not in names(agent.tools)


def test_autonomy_config_default_tools_appended_even_with_tools():
    agent = make(autonomy=AutonomyConfig(default_tools=[my_tool]), tools=[len])
    assert agent.tools == [len, my_tool]


def test_autonomy_config_empty_default_tools_injects_nothing():
    assert make(autonomy=AutonomyConfig(default_tools=[])).tools == []


# --- plugin tool merge ------------------------------------------------------------

def test_plugin_tools_merged_when_agent_has_none(tool_plugin):
    assert make().tools == [plugin_tool, plugin_my_tool]


def test_existing_tool_wins_name_collision_with_plugin(tool_plugin, caplog):
    with caplog.at_level(logging.WARNING):
        agent = make(tools=[my_tool])
    assert agent.tools == [my_tool, plugin_tool]
    assert "already has a tool with that name" in caplog.text


def test_plugin_tools_appended_after_autonomy_defaults(tool_plugin):
    tools = make(autonomy=True).tools
    assert names(tools)[0] == "ast_grep_search"
    assert tools[-1] is plugin_my_tool


def test_disabled_plugin_contributes_no_tools(tool_plugin):
    tool_plugin.disable("char_tools")
    assert make().tools == []


def test_non_list_tools_normalised_when_plugin_tool_added(tool_plugin):
    spec = {"type": "web_search"}
    assert make(tools=spec).tools == [spec, plugin_tool, plugin_my_tool]


# --- tool output limit ------------------------------------------------------------

@pytest.mark.parametrize("output, tool_config, expected", [
    (None, None, 16000),
    (OutputConfig(tool_output_limit=123), None, 123),
    (OutputConfig(tool_output_limit=123), False, 123),
    (OutputConfig(tool_output_limit=123), True, 16000),
    (OutputConfig(tool_output_limit=123), ToolConfig(), 16000),
    (OutputConfig(tool_output_limit=123), ToolConfig(output_limit=77), 77),
])
def test_tool_config_output_limit_wins_over_output_config(output, tool_config, expected):
    agent = make(output=output, tool_config=tool_config)
    assert agent.tool_output_limit == expected
