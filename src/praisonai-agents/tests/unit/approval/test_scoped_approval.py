"""
Tests for scoped interactive tool-approval decisions (once/session/always).

Covers:
- ``ApprovalDecision.scope`` defaults to ``"once"`` (backward compatible).
- ``build_permission_target`` maps tool calls to permission targets.
- ``ConsoleBackend`` returns the chosen scope from the interactive prompt.
- The registry bridges ``session``/``always`` decisions into the durable
  ``PermissionManager`` store so future ``check()`` calls short-circuit.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ── ApprovalDecision.scope ──────────────────────────────────────────────────


class TestApprovalDecisionScope:
    def test_scope_defaults_to_once(self):
        from praisonaiagents.approval.protocols import ApprovalDecision

        decision = ApprovalDecision(approved=True)
        assert decision.scope == "once"
        assert decision.scope_pattern is None

    def test_scope_can_be_set(self):
        from praisonaiagents.approval.protocols import ApprovalDecision

        decision = ApprovalDecision(
            approved=True, scope="always", scope_pattern="edit:src/app.py"
        )
        assert decision.scope == "always"
        assert decision.scope_pattern == "edit:src/app.py"


# ── build_permission_target ─────────────────────────────────────────────────


class TestBuildPermissionTarget:
    def test_shell_tool(self):
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target(
            "execute_command", {"command": "git status -s"}
        )
        assert target == "bash:git status -s"

    def test_file_edit_tool(self):
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target("edit_file", {"file_path": "src/app.py"})
        assert target == "edit:src/app.py"

    def test_apply_patch_stays_tool_scoped(self):
        # ``apply_patch`` takes ``patch`` (multi-file patch text), not a single
        # path, so it must NOT collapse to a path target that could silently
        # cover unrelated files on reuse — it stays ``tool:apply_patch``.
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target(
            "apply_patch", {"patch": "*** Begin Patch\n*** Update File: a/b.py"}
        )
        assert target == "tool:apply_patch"

    def test_move_file_uses_src_path(self):
        # ``move_file``/``copy_file`` take ``src``/``dst`` — the grant must pin
        # to the concrete source path, not fall back to ``tool:move_file``.
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target(
            "move_file", {"src": "a/old.py", "dst": "a/new.py"}
        )
        assert target == "move:a/old.py"

    def test_copy_file_uses_src_path(self):
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target(
            "copy_file", {"src": "a/x.py", "dst": "b/x.py"}
        )
        assert target == "copy:a/x.py"

    def test_unknown_tool_falls_back(self):
        from praisonaiagents.approval.utils import build_permission_target

        assert build_permission_target("scrape_page", {}) == "tool:scrape_page"

    def test_missing_argument_falls_back(self):
        from praisonaiagents.approval.utils import build_permission_target

        assert build_permission_target("edit_file", {}) == "tool:edit_file"


# ── ConsoleBackend scoped prompt ────────────────────────────────────────────


class TestConsoleBackendScope:
    def _make_request(self, **overrides):
        from praisonaiagents.approval.protocols import ApprovalRequest

        defaults = {
            "tool_name": "edit_file",
            "arguments": {"file_path": "src/app.py"},
            "risk_level": "high",
        }
        defaults.update(overrides)
        return ApprovalRequest(**defaults)

    @pytest.mark.parametrize(
        "choice,expected_scope,expected_approved",
        [
            ("o", "once", True),
            ("s", "session", True),
            ("a", "always", True),
            ("n", "once", False),
        ],
    )
    def test_prompt_returns_scope(self, choice, expected_scope, expected_approved):
        from praisonaiagents.approval.backends import ConsoleBackend

        backend = ConsoleBackend()
        request = self._make_request()

        with patch(
            "praisonaiagents.approval.backends._get_rich_console"
        ), patch(
            "praisonaiagents.approval.backends._get_rich_panel"
        ), patch(
            "praisonaiagents.approval.backends._get_rich_prompt"
        ) as mock_prompt:
            mock_prompt.return_value.ask.return_value = choice
            decision = backend.request_approval_sync(request)

        assert decision.approved is expected_approved
        assert decision.scope == expected_scope

    def test_always_carries_suggested_pattern(self):
        from praisonaiagents.approval.backends import ConsoleBackend

        backend = ConsoleBackend()
        request = self._make_request(
            tool_name="execute_command", arguments={"command": "git status -s"}
        )

        with patch(
            "praisonaiagents.approval.backends._get_rich_console"
        ), patch(
            "praisonaiagents.approval.backends._get_rich_panel"
        ), patch(
            "praisonaiagents.approval.backends._get_rich_prompt"
        ) as mock_prompt:
            mock_prompt.return_value.ask.return_value = "a"
            decision = backend.request_approval_sync(request)

        assert decision.approved is True
        assert decision.scope == "always"
        assert decision.scope_pattern == "bash:git status *"


# ── Registry → PermissionManager bridge ─────────────────────────────────────


class TestRegistryScopeBridge:
    def test_always_persists_to_manager(self, tmp_path):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision
        from praisonaiagents.permissions import PermissionManager

        registry = ApprovalRegistry()
        decision = ApprovalDecision(
            approved=True, scope="always", scope_pattern="edit:src/app.py"
        )

        with patch(
            "praisonaiagents.permissions.PermissionManager"
        ) as mock_mgr_cls:
            mgr = PermissionManager(storage_dir=str(tmp_path), agent_name="worker")
            mock_mgr_cls.return_value = mgr
            registry._persist_scoped_decision(
                "worker", "edit_file", {"file_path": "src/app.py"}, decision
            )

        result = mgr.check("edit:src/app.py", agent_name="worker")
        from praisonaiagents.permissions import PermissionAction

        assert result.action == PermissionAction.ALLOW

    def test_once_does_not_persist(self, tmp_path):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision
        from praisonaiagents.permissions import PermissionManager, PermissionAction

        registry = ApprovalRegistry()
        decision = ApprovalDecision(approved=True, scope="once")

        with patch(
            "praisonaiagents.permissions.PermissionManager"
        ) as mock_mgr_cls:
            mgr = PermissionManager(storage_dir=str(tmp_path), agent_name="worker")
            mock_mgr_cls.return_value = mgr
            registry._persist_scoped_decision(
                "worker", "edit_file", {"file_path": "src/app.py"}, decision
            )

        result = mgr.check("edit:src/app.py", agent_name="worker")
        assert result.action == PermissionAction.ASK

    def test_always_shell_grant_covers_variants(self, tmp_path):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision
        from praisonaiagents.permissions import PermissionManager, PermissionAction

        registry = ApprovalRegistry()
        decision = ApprovalDecision(
            approved=True, scope="always", scope_pattern="bash:git status *"
        )

        with patch(
            "praisonaiagents.permissions.PermissionManager"
        ) as mock_mgr_cls:
            mgr = PermissionManager(storage_dir=str(tmp_path), agent_name="worker")
            mock_mgr_cls.return_value = mgr
            registry._persist_scoped_decision(
                "worker",
                "execute_command",
                {"command": "git status -s"},
                decision,
            )

        # A different trailing arg is now covered by the reusable pattern.
        result = mgr.check("bash:git status .", agent_name="worker")
        assert result.action == PermissionAction.ALLOW

    def test_session_does_not_persist_to_disk(self):
        # "this session" grants must stay in-memory only — never written to
        # ``approvals.json`` (which would reload and outlive the run).
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision

        registry = ApprovalRegistry()
        decision = ApprovalDecision(approved=True, scope="session")

        with patch("praisonaiagents.permissions.PermissionManager") as mock_mgr_cls:
            registry._persist_scoped_decision(
                "worker", "edit_file", {"file_path": "src/app.py"}, decision
            )
            # PermissionManager (durable store) must never be touched for session.
            mock_mgr_cls.assert_not_called()

        # ...but the in-memory session store now covers the matching call.
        assert registry._is_session_scoped(
            "worker", "edit_file", {"file_path": "src/app.py"}
        )

    def test_session_scope_cleared_by_clear_approved(self):
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision

        registry = ApprovalRegistry()
        registry._persist_scoped_decision(
            "worker",
            "edit_file",
            {"file_path": "src/app.py"},
            ApprovalDecision(approved=True, scope="session"),
        )
        assert registry._is_session_scoped(
            "worker", "edit_file", {"file_path": "src/app.py"}
        )
        registry.clear_approved()
        assert not registry._is_session_scoped(
            "worker", "edit_file", {"file_path": "src/app.py"}
        )

    def test_nameless_always_not_persisted(self):
        # An ``always`` grant without an agent name must NOT be persisted (it
        # would match any later agent); it degrades to in-memory session scope.
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision

        registry = ApprovalRegistry()
        decision = ApprovalDecision(approved=True, scope="always")

        with patch("praisonaiagents.permissions.PermissionManager") as mock_mgr_cls:
            registry._persist_scoped_decision(
                None, "edit_file", {"file_path": "src/app.py"}, decision
            )
            mock_mgr_cls.assert_not_called()

        assert registry._is_session_scoped(
            None, "edit_file", {"file_path": "src/app.py"}
        )

    def test_session_scope_is_target_scoped(self):
        # A session grant is keyed by the exact permission target, so the same
        # command is covered but a different command still prompts.
        from praisonaiagents.approval.registry import ApprovalRegistry
        from praisonaiagents.approval.protocols import ApprovalDecision

        registry = ApprovalRegistry()
        registry._persist_scoped_decision(
            "worker",
            "execute_command",
            {"command": "git status -s"},
            ApprovalDecision(approved=True, scope="session"),
        )
        assert registry._is_session_scoped(
            "worker", "execute_command", {"command": "git status -s"}
        )
        # A different command is NOT auto-covered by the session grant.
        assert not registry._is_session_scoped(
            "worker", "execute_command", {"command": "rm -rf /"}
        )
