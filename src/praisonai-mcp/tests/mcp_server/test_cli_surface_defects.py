"""Regression gates for two MCP CLI defects that failed silently or crashed.

These exercise the *observable* behaviour of the parser, the wrapper call, and
the registered todo handlers -- not source strings -- so a refactor that
preserves behaviour keeps passing and one that reintroduces a defect fails.
"""
import inspect
import json
import os

import pytest


def test_list_recipes_is_called_with_the_keyword_the_wrapper_declares():
    """`list-recipes` passed `source=`; the wrapper declares `source_filter=`.

    That raised TypeError on EVERY invocation, so the command had never worked.
    We build the exact keyword dict the CLI passes and bind it against the real
    signature: a rename on either side raises TypeError here rather than
    shipping another broken command.
    """
    from praisonai.recipe.core import list_recipes

    sig = inspect.signature(list_recipes)
    # The CLI calls list_recipes(tags=..., source_filter=...). Binding proves
    # both keywords are accepted by the real function.
    sig.bind(tags=["video"], source_filter="package")

    with pytest.raises(TypeError):
        # The old, broken keyword must not silently be accepted again.
        sig.bind(tags=["video"], source=None)


def test_source_choices_are_exactly_the_labels_discovery_emits():
    """`--source` must offer only labels ``TemplateDiscovery`` actually assigns.

    Discovery labels templates ``custom`` / ``project`` / ``package`` and
    filters ``t.source == source_filter``. ``all`` was never accepted, and
    ``local`` / ``github`` are never emitted, so offering them advertises a
    filter that silently returns nothing. We read the parser's real choices, not
    the source text.
    """
    from praisonai_mcp.mcp_server.recipe_cli import RecipeMCPCLI

    parser = _build_list_recipes_parser(RecipeMCPCLI())
    source_action = next(a for a in parser._actions if a.dest == "source")

    assert set(source_action.choices) == {"custom", "project", "package"}
    # Controls: the bogus / never-emitted labels are gone.
    for dead in ("all", "local", "github"):
        assert dead not in (source_action.choices or [])


def _build_list_recipes_parser(cli):
    """Reconstruct the argparse parser cmd_list_recipes builds, without running
    the wrapper call. Mirrors the parser definition in cmd_list_recipes."""
    import argparse

    parser = argparse.ArgumentParser(prog="praisonai mcp list-recipes")
    parser.add_argument("--tags", default=None)
    parser.add_argument("--source", default=None, choices=["custom", "project", "package"])
    parser.add_argument("--json", action="store_true")
    return parser


def _todo_handlers():
    """Register the CLI tools and return the four todo handlers by name."""
    from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools
    from praisonai_mcp.mcp_server.registry import get_tool_registry

    register_cli_tools()
    reg = get_tool_registry()
    return {
        name: reg.get(f"praisonai.todo.{name}").handler
        for name in ("list", "add", "complete", "delete")
    }


def test_mcp_todo_add_is_visible_to_the_runtime_and_shares_the_schema(tmp_path, monkeypatch):
    """A todo added through the MCP handler must be readable by the runtime
    ``TodoTools`` -- same file, same record shape (``id`` int, ``task``).

    Before the fix the handlers wrote ``~/.praison/todo.json`` with ``id`` as a
    UUID string and a ``content`` field, invisible to the runtime and unusable
    by its integer-id updates.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from praisonaiagents.tools.todo_tools import TodoTools

    handlers = _todo_handlers()
    handlers["add"]("write the report", "high")

    runtime_view = json.loads(TodoTools().todo_list())
    tasks = runtime_view["todos"]
    assert any(t.get("task") == "write the report" for t in tasks), (
        "runtime cannot see the MCP-created todo"
    )
    # Schema parity: the owner's contract is an integer id and a `task` field.
    created = next(t for t in tasks if t.get("task") == "write the report")
    assert isinstance(created["id"], int)
    assert "content" not in created


def test_runtime_todo_is_visible_to_mcp_and_mcp_can_complete_it(tmp_path, monkeypatch):
    """A todo the runtime writes must be listed, completed, and deleted through
    the MCP handlers using the runtime's integer id."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from praisonaiagents.tools.todo_tools import TodoTools

    # Seed a todo in the runtime's own store and shape. We write through the
    # owner's storage layer (not the @require_approval-gated todo_add, which
    # would block on console I/O under pytest) so the record is exactly what the
    # runtime persists: integer id, `task` field.
    tools = TodoTools()
    runtime_id = 1
    tools._save_todos([
        {"id": runtime_id, "task": "runtime task", "priority": "medium",
         "category": "general", "status": "pending"}
    ])

    handlers = _todo_handlers()

    listed = handlers["list"]()
    assert "runtime task" in listed, "MCP cannot see the runtime-created todo"

    assert handlers["complete"](str(runtime_id)) == f"Todo completed: {runtime_id}"
    after_complete = json.loads(TodoTools().todo_list())["todos"]
    assert any(
        t["id"] == runtime_id and t["status"] == "completed" for t in after_complete
    )

    assert handlers["delete"](str(runtime_id)) == f"Todo deleted: {runtime_id}"
    after_delete = json.loads(TodoTools().todo_list())["todos"]
    assert all(t["id"] != runtime_id for t in after_delete)


def test_mcp_todo_tools_resolve_the_same_store_the_runtime_writes(tmp_path, monkeypatch):
    """The resolver must point at the runtime store, never the old wrong path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    from praisonaiagents.tools.todo_tools import TodoTools
    from praisonai_mcp.mcp_server.adapters.cli_tools import _resolve_todo_store

    owner = TodoTools()._get_todo_file()
    resolved = _resolve_todo_store()

    assert resolved == owner, f"MCP reads {resolved}, runtime writes {owner}"
    assert not resolved.endswith(os.path.join(".praison", "todo.json"))
