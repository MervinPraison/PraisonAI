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

    def test_apply_patch_maps_to_edit(self):
        from praisonaiagents.approval.utils import build_permission_target

        target = build_permission_target("apply_patch", {"path": "a/b.py"})
        assert target == "edit:a/b.py"

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
