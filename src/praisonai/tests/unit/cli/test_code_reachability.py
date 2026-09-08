"""Capabilities that existed in the monorepo but the code session could not reach.

Each test here failed on origin/main:

* ``/compact`` toggled a *display* flag; ``features/context_manager.py`` (token
  budgeting, optimizer strategies, ``should_auto_compact``) was imported only by
  the legacy interactive path, never by the modern TUI.
* ``/map`` printed "Generating repository map..." and returned without
  generating one, while ``features/repo_map.py`` worked.
* the code session built no MCP tools, though ``commands/run.py`` already had
  ``_collect_mcp_servers_from_config`` and ``_build_mcp_tools``.
"""

import pytest


def _tui():
    mod = pytest.importorskip("praisonai_code.cli.interactive.async_tui")
    return mod


# ---------------------------------------------------------------------------
# /compact -- real context compaction
# ---------------------------------------------------------------------------

def _long_history(n=120):
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "x " * 4000}
        for i in range(n)
    ]


def test_compact_shrinks_the_model_context_not_a_display_flag():
    mod = _tui()
    tui = mod.AsyncTUI()
    before_flag = tui.config.compact_mode
    tui._conversation_history = _long_history()

    handled = tui._handle_command("/compact")

    assert handled is True
    # The display flag must be untouched -- that is what /compact-display is for.
    assert tui.config.compact_mode is before_flag
    assert len(tui._conversation_history) < 120, "context was not actually compacted"
    assert any(
        "Compacted context" in m.content
        for m in tui.messages
        if m.role == "system"
    ), [m.content for m in tui.messages]


def test_compact_display_still_toggles_the_display_flag():
    mod = _tui()
    tui = mod.AsyncTUI()
    before = tui.config.compact_mode
    assert tui._handle_command("/compact-display") is True
    assert tui.config.compact_mode is (not before)
    assert tui._handle_command("/dense") is True
    assert tui.config.compact_mode is before


def test_compact_reports_when_there_is_nothing_to_do():
    mod = _tui()
    tui = mod.AsyncTUI()
    tui._conversation_history = [{"role": "user", "content": "hi"}]
    assert tui._handle_command("/compact") is True
    assert any("Not enough history" in m.content for m in tui.messages)


def test_auto_compact_triggers_at_the_turn_boundary():
    """``should_auto_compact`` existed and was never called from the TUI."""
    mod = _tui()
    tui = mod.AsyncTUI()
    tui._conversation_history = _long_history()
    tui._maybe_auto_compact()
    assert len(tui._conversation_history) < 120


def test_auto_compact_is_a_noop_on_a_short_session():
    mod = _tui()
    tui = mod.AsyncTUI()
    tui._conversation_history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    tui._maybe_auto_compact()
    assert len(tui._conversation_history) == 2
    assert not tui.messages


def test_help_advertises_both_compact_commands():
    mod = _tui()
    tui = mod.AsyncTUI()
    assert tui._handle_command("/help") is True
    text = "\n".join(m.content for m in tui.messages)
    assert "/compact-display" in text
    assert "/compact " in text or "/compact\n" in text


# ---------------------------------------------------------------------------
# /map -- repository map
# ---------------------------------------------------------------------------

def test_map_actually_generates_a_map(tmp_path):
    sc = pytest.importorskip("praisonai_code.cli.features.slash_commands")
    (tmp_path / "sample.py").write_text(
        "class Widget:\n"
        "    def spin(self):\n"
        "        return 1\n\n"
        "def make_widget():\n"
        "    return Widget()\n"
    )
    ctx = sc.CommandContext()
    result = sc.cmd_map(ctx, str(tmp_path))
    assert result["success"] is True
    assert result["map"], "cmd_map returned no map"
    assert "sample.py" in result["map"]


def test_map_reports_failure_instead_of_a_silent_empty_result(tmp_path):
    sc = pytest.importorskip("praisonai_code.cli.features.slash_commands")
    empty = tmp_path / "empty"
    empty.mkdir()
    result = sc.cmd_map(sc.CommandContext(), str(empty))
    # Either way it must say what happened rather than returning a bare marker.
    assert "success" in result


# ---------------------------------------------------------------------------
# MCP in the code session
# ---------------------------------------------------------------------------

def test_interactive_tools_expose_an_mcp_group():
    it = pytest.importorskip("praisonai_code.cli.features.interactive_tools")
    assert "mcp" in it.TOOL_GROUPS


def test_mcp_builder_is_reused_from_run_py():
    """No second MCP builder: the code session calls run.py's."""
    it = pytest.importorskip("praisonai_code.cli.features.interactive_tools")
    import inspect

    src = inspect.getsource(it)
    assert "_collect_mcp_servers_from_config" in src
    assert "_build_mcp_tools" in src


def test_mcp_tools_load_without_servers_configured(tmp_path, monkeypatch):
    """No MCP config must mean zero tools, not an exception."""
    it = pytest.importorskip("praisonai_code.cli.features.interactive_tools")
    monkeypatch.chdir(tmp_path)
    tools = it._load_mcp_tools()
    assert tools == {}


_TINY_MCP_SERVER = """
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tiny")


@mcp.tool()
def tiny_add(a: int, b: int) -> int:
    \"\"\"Add two integers.\"\"\"
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
"""

_TINY_MCP_CONFIG = """
mcp:
  servers:
    tiny:
      command: python3
      args: ["tiny_mcp_server.py"]
      enabled: true
"""


@pytest.mark.timeout(120)
def test_mcp_server_from_project_config_reaches_the_code_session(tmp_path, monkeypatch):
    """End-to-end: a configured stdio server yields a callable in the tool set.

    Before this change the code session built zero MCP tools regardless of
    config, so this asserts the tool is actually present -- not that a builder
    exists.
    """
    pytest.importorskip("mcp.server.fastmcp")
    it = pytest.importorskip("praisonai_code.cli.features.interactive_tools")

    (tmp_path / "tiny_mcp_server.py").write_text(_TINY_MCP_SERVER)
    (tmp_path / "praisonai.yaml").write_text(_TINY_MCP_CONFIG)
    monkeypatch.chdir(tmp_path)
    # The config resolver is a process-wide singleton with a cache; a prior test
    # in this file may already have resolved a config for a different cwd.
    from praisonai_code.cli.configuration.resolver import get_resolver

    get_resolver(tmp_path, reset=True)

    loaded = it._load_mcp_tools()
    assert "tiny_add" in loaded, f"MCP tool not reachable; got {list(loaded)}"

    tools = it.get_interactive_tools(groups=["mcp"], workspace=str(tmp_path))
    names = [getattr(t, "__name__", getattr(t, "name", None)) for t in tools]
    assert "tiny_add" in names


def test_mcp_group_reaches_the_tui_and_headless_paths():
    """Both code-session entry points must request the mcp group."""
    import inspect

    tui = pytest.importorskip("praisonai_code.cli.interactive.async_tui")
    code = pytest.importorskip("praisonai_code.cli.commands.code")
    assert '"mcp"' in inspect.getsource(tui.AsyncTUI._load_tools)
    assert '"mcp"' in inspect.getsource(code)


def test_mcp_group_honours_the_standard_disable_flag(monkeypatch):
    it = pytest.importorskip("praisonai_code.cli.features.interactive_tools")
    monkeypatch.setenv("PRAISON_TOOLS_DISABLE", "mcp")
    cfg = it.ToolConfig()
    assert cfg.enable_mcp is False


# ---------------------------------------------------------------------------
# GitManager -- given a surface, and its status parser fixed
# ---------------------------------------------------------------------------

def _init_repo(path):
    import subprocess

    def run(*args):
        return subprocess.run(
            ["git", *args], cwd=str(path), capture_output=True, text=True, check=True
        )

    run("init", "-q", ".")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    (path / "a.txt").write_text("hello\n")
    run("add", "a.txt")
    run("commit", "-qm", "init")
    return run


def test_git_status_does_not_mangle_an_unstaged_path(tmp_path):
    """``stdout.strip()`` ate the first porcelain line's leading space.

    " M a.txt" parsed as status "M " and path ".txt", so a *modified* file was
    reported as *staged* under a truncated name.
    """
    gi = pytest.importorskip("praisonai_code.cli.features.git_integration")
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello\nworld\n")

    status = gi.GitManager(repo_path=str(tmp_path)).get_status()

    assert status.modified_files == ["a.txt"]
    assert status.staged_files == []


def test_git_status_handles_a_staged_file(tmp_path):
    gi = pytest.importorskip("praisonai_code.cli.features.git_integration")
    run = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello\nworld\n")
    run("add", "a.txt")

    status = gi.GitManager(repo_path=str(tmp_path)).get_status()

    assert status.staged_files == ["a.txt"]


def test_git_commands_are_reachable_from_the_session(tmp_path):
    """GitManager had exactly one caller: /code-review, to collect a diff."""
    mod = _tui()
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("hello\nworld\n")

    tui = mod.AsyncTUI(config=mod.AsyncTUIConfig(workspace=str(tmp_path)))

    assert tui._handle_command("/git-status") is True
    assert "a.txt" in tui.messages[-1].content

    tui.messages.clear()
    assert tui._handle_command("/git-diff") is True
    assert "+world" in tui.messages[-1].content

    tui.messages.clear()
    assert tui._handle_command("/git-commit add world") is True
    assert "Committed" in tui.messages[-1].content

    tui.messages.clear()
    assert tui._handle_command("/git-log 5") is True
    assert "add world" in tui.messages[-1].content

    tui.messages.clear()
    assert tui._handle_command("/git-undo") is True
    assert "Undid" in tui.messages[-1].content


def test_git_commands_report_when_not_a_repo(tmp_path):
    mod = _tui()
    tui = mod.AsyncTUI(config=mod.AsyncTUIConfig(workspace=str(tmp_path)))
    assert tui._handle_command("/git-status") is True
    assert "Not a git repository" in tui.messages[-1].content
