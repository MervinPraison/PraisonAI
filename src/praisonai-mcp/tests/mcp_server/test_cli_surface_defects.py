"""Regression gates for two MCP CLI defects that failed silently or crashed.

Both assert against the *owning* definition rather than a corrected literal:
a test pinning the fixed string would drift the same way the bugs did.
"""
import inspect
import os

import pytest


def test_list_recipes_is_called_with_the_keyword_the_wrapper_declares():
    """`list-recipes` passed `source=`; the wrapper declares `source_filter=`.

    That raised TypeError on EVERY invocation, so the command had never worked.
    Asserting against the real signature means renaming the wrapper parameter
    fails this test rather than shipping another broken command.
    """
    from praisonai.recipe.core import list_recipes
    from praisonai_mcp.mcp_server import recipe_cli

    accepted = set(inspect.signature(list_recipes).parameters)
    src = inspect.getsource(recipe_cli.RecipeMCPCLI.cmd_list_recipes)

    assert "source_filter=" in src, "must pass the wrapper's real keyword"
    assert "source=parsed.source" not in src, "the TypeError-raising call is back"
    assert "source_filter" in accepted, "wrapper renamed its parameter"


def test_source_choices_match_what_the_wrapper_accepts():
    """`--source` offered `all`, which the wrapper has never accepted, and
    omitted `github`, which it does."""
    from praisonai_mcp.mcp_server import recipe_cli

    src = inspect.getsource(recipe_cli.RecipeMCPCLI)
    assert '"github"' in src, "github is a real source and must be offered"
    assert '"local", "package", "all"' not in src, "the bogus 'all' choice is back"


def test_mcp_todo_tools_resolve_the_same_store_the_runtime_writes(tmp_path, monkeypatch):
    """The MCP tools hardcoded ~/.praison/todo.json -- wrong directory AND
    wrong filename -- so `praisonai.todo.list` answered "No todos found" to a
    user who had todos, and `todo.add` started a second, invisible list.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from praisonaiagents.tools.todo_tools import TodoTools
    from praisonai_mcp.mcp_server.adapters.cli_tools import _resolve_todo_store

    owner = TodoTools()._get_todo_file()
    resolved = _resolve_todo_store()

    assert resolved == owner, f"MCP reads {resolved}, runtime writes {owner}"
    # Control: the resolved path must not be the old, wrong one.
    assert not resolved.endswith(os.path.join(".praison", "todo.json"))


def test_no_hardcoded_todo_path_remains():
    """Control gate: the four literals are gone, so they cannot drift again."""
    from praisonai_mcp.mcp_server.adapters import cli_tools

    src = inspect.getsource(cli_tools)
    assert '"~/.praison/todo.json"' not in src, "a hardcoded todo path is back"
    assert src.count("_resolve_todo_store()") >= 4, "call sites were removed"
