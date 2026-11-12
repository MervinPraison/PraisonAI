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

    def test_shell_target_preserves_command_identity(self, tmp_path, monkeypatch):
        # The shell target is always ``bash:<command>`` verbatim — including for
        # out-of-workspace commands — so command-specific rules (e.g.
        # ``deny: bash:rm *``) can still match. The out-of-workspace boundary is
        # enforced downstream by ``PermissionManager`` (see the boundary tests
        # below), NOT by mangling the target into a path-only namespace (which
        # would silently evade command-scoped deny rules).
        from praisonaiagents.approval.utils import build_permission_target

        monkeypatch.chdir(tmp_path)
        assert (
            build_permission_target("execute_command", {"command": "cat ./notes.txt"})
            == "bash:cat ./notes.txt"
        )
        assert (
            build_permission_target("execute_command", {"command": "cat /etc/passwd"})
            == "bash:cat /etc/passwd"
        )
        assert (
            build_permission_target(
                "execute_command", {"command": "echo hi > /tmp/evil.txt"}
            )
            == "bash:echo hi > /tmp/evil.txt"
        )


# ── Workspace-boundary enforcement (PermissionManager) ──────────────────────


class TestShellWorkspaceBoundary:
    """The out-of-workspace boundary is enforced by ``PermissionManager`` on the
    plain ``bash:<command>`` target, so a broad ``bash:*`` / "allow shell" /
    session grant cannot silently authorise external paths *and* a
    command-specific ``deny`` still fires (no target-namespace evasion)."""

    def _mgr(self, tmp_path, rule_pattern, action):
        from praisonaiagents.permissions import (
            PermissionManager,
            PermissionAction,
        )
        from praisonaiagents.permissions.rules import PermissionRule

        mgr = PermissionManager(
            storage_dir=str(tmp_path / "perm"),
            agent_name="w",
            workspace_root=str(tmp_path / "ws"),
        )
        mgr.add_rule(
            PermissionRule(pattern=rule_pattern, action=PermissionAction(action))
        )
        return mgr

    def test_broad_allow_does_not_cover_external_path(self, tmp_path):
        # PR core goal: ``bash:*`` allow must NOT silently authorise a command
        # touching a path outside the workspace — it escalates to ASK.
        from praisonaiagents.permissions import PermissionAction

        mgr = self._mgr(tmp_path, "bash:*", "allow")
        result = mgr.check("bash:cat /etc/passwd", agent_name="w")
        assert result.action == PermissionAction.ASK

    def test_broad_allow_still_covers_in_workspace(self, tmp_path):
        # In-workspace commands under a broad allow are unchanged (no regression).
        from praisonaiagents.permissions import PermissionAction

        ws = tmp_path / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        mgr = self._mgr(tmp_path, "bash:*", "allow")
        result = mgr.check(f"bash:cat {ws}/notes.txt", agent_name="w")
        assert result.action == PermissionAction.ALLOW

    def test_command_deny_still_fires_on_external_path(self, tmp_path):
        # Regression guard for the reviewer-reported bypass: an explicit
        # ``deny: bash:rm *`` MUST still win even when the path is external —
        # the target must keep its command identity so the deny matches.
        from praisonaiagents.permissions import PermissionAction

        mgr = self._mgr(tmp_path, "bash:rm *", "deny")
        result = mgr.check("bash:rm /tmp/evil.txt", agent_name="w")
        assert result.action == PermissionAction.DENY

    def test_no_workspace_root_is_backward_compatible(self, tmp_path):
        # Backward-compat: with no ``workspace_root`` configured, the boundary
        # stays off and a broad allow covers the external command (unchanged).
        from praisonaiagents.permissions import (
            PermissionManager,
            PermissionAction,
        )
        from praisonaiagents.permissions.rules import PermissionRule

        mgr = PermissionManager(storage_dir=str(tmp_path / "perm"), agent_name="w")
        assert mgr.workspace_root is None
        mgr.add_rule(
            PermissionRule(pattern="bash:*", action=PermissionAction("allow"))
        )
        result = mgr.check("bash:cat /etc/passwd", agent_name="w")
        assert result.action == PermissionAction.ALLOW


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

    def test_deny_with_guidance_captures_feedback(self):
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
            mock_prompt.return_value.ask.side_effect = [
                "d",
                "edit tests/app.py instead",
            ]
            decision = backend.request_approval_sync(request)

        assert decision.approved is False
        assert decision.feedback == "edit tests/app.py instead"
        assert "edit tests/app.py instead" in decision.reason

    def test_plain_deny_has_no_feedback(self):
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
            mock_prompt.return_value.ask.return_value = "n"
            decision = backend.request_approval_sync(request)

        assert decision.approved is False
        assert decision.feedback is None
        assert decision.reason == "User denied"


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


class TestContextCacheScopeId:
    """The in-context ``is_already_approved`` cache must be keyed per-instance
    (``scope_id``) so a grant marked on one worker cannot pre-authorize a
    distinct same-named worker sharing the execution context — the fast-path
    checked *before* the per-instance session lookup.
    """

    def test_context_cache_isolated_by_scope_id(self):
        from praisonaiagents.approval.registry import ApprovalRegistry

        registry = ApprovalRegistry()
        args = {"command": "git status"}

        # Two workers share the display name "Agent" but have distinct scope ids.
        registry.mark_approved("execute_command", args, "Agent", scope_id="inst-A")

        # Same instance sees its own grant.
        assert registry.is_already_approved(
            "execute_command", args, "Agent", scope_id="inst-A"
        )
        # A distinct same-named instance must NOT inherit it.
        assert not registry.is_already_approved(
            "execute_command", args, "Agent", scope_id="inst-B"
        )

    def test_name_keyed_fallback_preserved(self):
        # With no scope_id supplied, behaviour falls back to name-keyed caching
        # (backward compatible).
        from praisonaiagents.approval.registry import ApprovalRegistry

        registry = ApprovalRegistry()
        args = {"command": "git status"}
        registry.mark_approved("execute_command", args, "worker")
        assert registry.is_already_approved("execute_command", args, "worker")
        assert not registry.is_already_approved("execute_command", args, "other")


# ── @require_approval positional-argument scoping ───────────────────────────


class TestRequireApprovalPositionalScoping:
    """A single approval must not unlock a decorated tool for *other* argument
    values — including when the tool is invoked with positional args.
    """

    def test_positional_call_is_argument_scoped(self, monkeypatch):
        # One env auto-approved positional call must NOT unlock a different
        # positional value on the same tool.
        from praisonaiagents.approval import (
            require_approval,
            is_already_approved,
            _bind_call_args,
            clear_approval_context,
        )

        clear_approval_context()
        monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")

        @require_approval(risk_level="high")
        def read_secret(path):
            return f"read {path}"

        read_secret("/tmp/notes.txt")

        assert is_already_approved(
            "read_secret", _bind_call_args(read_secret, ("/tmp/notes.txt",), {})
        )
        # A different positional value must still require approval.
        assert not is_already_approved(
            "read_secret", _bind_call_args(read_secret, ("/etc/cron.d/evil",), {})
        )

    def test_bind_call_args_matches_positional_and_keyword(self):
        # Calling positionally vs by keyword for the same value yields the same
        # approval key, so an approval granted one way is honoured the other.
        from praisonaiagents.approval import _bind_call_args

        def tool(path, mode="r"):
            return path

        assert _bind_call_args(tool, ("/a",), {}) == _bind_call_args(
            tool, (), {"path": "/a"}
        )

    def test_bind_call_args_falls_back_for_builtin(self):
        # C-implemented callables have no bindable signature; distinct positional
        # calls must still yield distinct keys (via ``__args__``), never collapse.
        from praisonaiagents.approval import _bind_call_args

        a = _bind_call_args(len, ("abc",), {})
        b = _bind_call_args(len, ("abcd",), {})
        assert a != b
