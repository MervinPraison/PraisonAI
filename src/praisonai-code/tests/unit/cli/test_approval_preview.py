"""Approval prompt must preview the concrete change for edit_file (issue #6298)."""

from praisonaiagents.approval import ApprovalRequest

from praisonai_code.cli.approval_backend import InteractiveCLIApprovalBackend
from praisonai_code.cli.interactive.events import render_change_preview


def _backend(tmp_path):
    return InteractiveCLIApprovalBackend(project_dir=str(tmp_path), non_interactive=True)


def test_edit_file_preview_is_contextual_diff(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("a = 1\nb = 2\nc = 3\n")
    args = {"filepath": str(target), "old_string": "b = 2", "new_string": "b = 42"}
    req = ApprovalRequest(tool_name="edit_file", arguments=args, risk_level="high")

    preview = _backend(tmp_path)._render_preview(req)

    assert preview is not None and "Preview (diff)" in preview
    assert "-b = 2" in preview and "+b = 42" in preview
    assert " a = 1" in preview  # surrounding on-disk context
    assert "+b = 42" in render_change_preview("edit_file", args)


def test_context_diff_used_when_not_computable(tmp_path):
    req = ApprovalRequest(
        tool_name="custom_mutator",
        arguments={"target": "x"},
        risk_level="high",
        context={"diff": "--- precomputed\n+++ precomputed\n"},
    )
    assert "precomputed" in _backend(tmp_path)._render_preview(req)


def test_non_mutating_tool_has_no_preview(tmp_path):
    req = ApprovalRequest(tool_name="execute_command", arguments={"command": "ls"}, risk_level="high")
    assert _backend(tmp_path)._render_preview(req) is None


def test_relative_path_resolves_under_workspace(tmp_path, monkeypatch):
    """Preview reads the workspace file, not a same-named file in the launch cwd."""
    workspace = tmp_path / "ws"
    launch = tmp_path / "launch"
    workspace.mkdir()
    launch.mkdir()
    (workspace / "app.py").write_text("ws_top\nb = 2\n")
    (launch / "app.py").write_text("cwd_top\nb = 2\n")
    monkeypatch.chdir(launch)
    monkeypatch.setenv("PRAISONAI_WORKSPACE", str(workspace))
    args = {"filepath": "app.py", "old_string": "b = 2", "new_string": "b = 42"}
    req = ApprovalRequest(tool_name="edit_file", arguments=args, risk_level="high")

    for preview in (_backend(launch)._render_preview(req), render_change_preview("edit_file", args)):
        assert " ws_top" in preview and "cwd_top" not in preview


def test_older_core_without_helper_does_not_crash(tmp_path, monkeypatch):
    import praisonaiagents.approval.utils as utils

    monkeypatch.delattr(utils, "build_diff_preview")
    req = ApprovalRequest(tool_name="execute_command", arguments={"command": "ls"}, risk_level="high")
    assert _backend(tmp_path)._render_preview(req) is None
    args = {"filepath": "a", "old_string": "o", "new_string": "n"}
    assert render_change_preview("edit_file", args) is None
