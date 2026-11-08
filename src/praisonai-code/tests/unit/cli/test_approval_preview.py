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


def test_context_diff_is_preferred(tmp_path):
    req = ApprovalRequest(
        tool_name="edit_file",
        arguments={"filepath": "x", "old_string": "o", "new_string": "n"},
        risk_level="high",
        context={"diff": "--- precomputed\n+++ precomputed\n"},
    )
    assert "precomputed" in _backend(tmp_path)._render_preview(req)


def test_non_mutating_tool_has_no_preview(tmp_path):
    req = ApprovalRequest(tool_name="execute_command", arguments={"command": "ls"}, risk_level="high")
    assert _backend(tmp_path)._render_preview(req) is None
