"""Tests for wiring the targeted/fuzzy edit engine into the default toolset (#2903).

The interactive coding agent must default to targeted string-replace edits
(``edit_file``) and atomic multi-file patches (``apply_patch``) backed by the
existing ``praisonaiagents.tools.edit_tools`` engine, instead of whole-file
rewrites. Whole-file creation (``write_file``/``acp_create_file``) must remain
available and ``--tools``/``PRAISON_TOOLS_DISABLE`` overrides must be honoured.
"""

import os

import pytest

from praisonai_code.cli.features.interactive_tools import (
    TOOL_GROUPS,
    ToolConfig,
    resolve_tool_groups,
    get_interactive_tools,
)

_engine_available = True
try:  # pragma: no cover - environment dependent
    import praisonaiagents.tools.edit_tools  # noqa: F401
except Exception:  # pragma: no cover
    _engine_available = False

requires_engine = pytest.mark.skipif(
    not _engine_available,
    reason="praisonaiagents edit_tools engine not installed",
)


def test_edit_group_defined():
    assert TOOL_GROUPS["edit"] == ["edit_file", "apply_patch"]


def test_edit_tools_in_default_interactive_group():
    assert "edit_file" in TOOL_GROUPS["interactive"]
    assert "apply_patch" in TOOL_GROUPS["interactive"]


def test_resolve_includes_edit_by_default():
    names = resolve_tool_groups()
    assert "edit_file" in names
    assert "apply_patch" in names


def test_resolve_edit_group_only():
    names = resolve_tool_groups(groups=["edit"])
    assert names == {"edit_file", "apply_patch"}


def test_disable_edit_via_config():
    cfg = ToolConfig()
    cfg.enable_edit = False
    names = resolve_tool_groups(config=cfg)
    assert "edit_file" not in names
    assert "apply_patch" not in names


def test_disable_edit_via_env(monkeypatch):
    monkeypatch.setenv("PRAISON_TOOLS_DISABLE", "edit")
    cfg = ToolConfig.from_env()
    assert cfg.enable_edit is False
    names = resolve_tool_groups(config=cfg)
    assert "edit_file" not in names


@requires_engine
def test_get_interactive_tools_loads_edit_engine(tmp_path):
    tools = get_interactive_tools(
        groups=["edit"],
        config=ToolConfig(workspace=str(tmp_path), approval_mode="auto"),
    )
    by_name = {t.__name__: t for t in tools}
    assert "edit_file" in by_name
    assert "apply_patch" in by_name


@requires_engine
def test_edit_file_performs_targeted_replacement(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text("def foo():\n    return 1\n")

    tools = get_interactive_tools(
        groups=["edit"],
        config=ToolConfig(workspace=str(tmp_path), approval_mode="auto"),
    )
    edit_file = {t.__name__: t for t in tools}["edit_file"]

    result = edit_file("sample.py", "return 1", "return 2")

    assert "Success" in result
    assert target.read_text() == "def foo():\n    return 2\n"


@requires_engine
def test_whole_file_creation_still_available(tmp_path):
    tools = get_interactive_tools(
        config=ToolConfig(workspace=str(tmp_path), approval_mode="auto"),
    )
    names = {t.__name__ for t in tools}
    # Targeted edit is present alongside whole-file creation paths.
    assert "edit_file" in names
    assert "write_file" in names


@requires_engine
def test_auto_approval_does_not_clobber_existing_approvals(tmp_path):
    """Auto-mode edit-tool approval must merge, not replace, the YAML set.

    Loading the edit tools in ``auto`` mode context-approves ``edit_file``/
    ``apply_patch`` so they don't block on a console prompt. It must preserve
    any previously approved workflow tools rather than overwriting the whole
    set (regression guard for the clobber/leak issue).
    """
    from praisonaiagents.approval import (
        get_approval_registry,
        set_yaml_approved_tools,
        reset_yaml_approved_tools,
    )

    reg = get_approval_registry()
    token = set_yaml_approved_tools(["my_workflow_tool"])
    try:
        get_interactive_tools(
            groups=["edit"],
            config=ToolConfig(workspace=str(tmp_path), approval_mode="auto"),
        )
        approved = reg._yaml_approved_tools.get()
        # Newly approved edit tools are present ...
        assert "edit_file" in approved
        assert "apply_patch" in approved
        # ... and the pre-existing approval is not clobbered.
        assert "my_workflow_tool" in approved
    finally:
        reset_yaml_approved_tools(token)


@requires_engine
def test_edit_tools_require_workspace_containment(monkeypatch, tmp_path):
    """Edit tools must fail closed when workspace containment is unavailable.

    The core engine's no-workspace fallback accepts absolute paths, which under
    auto-approval could escape the configured workspace, so the loader must not
    expose ``edit_file``/``apply_patch`` when the ``Workspace`` cannot be built.
    """
    import praisonaiagents.workspace as ws

    class _BrokenWorkspace:
        def __init__(self, *a, **k):
            raise RuntimeError("containment unavailable")

    monkeypatch.setattr(ws, "Workspace", _BrokenWorkspace)

    tools = get_interactive_tools(
        groups=["edit"],
        config=ToolConfig(workspace=str(tmp_path), approval_mode="auto"),
    )
    names = {t.__name__ for t in tools}
    assert "edit_file" not in names
    assert "apply_patch" not in names
