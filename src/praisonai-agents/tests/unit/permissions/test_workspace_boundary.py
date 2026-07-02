"""
Tests for workspace-boundary enforcement (external_dir gating).

Verifies that shell/file targets resolving outside the configured
``workspace_root`` emit a distinct ``external_dir:`` approval (default ``ask``),
while in-workspace operations behave exactly as before and, when no
``workspace_root`` is configured, behaviour is unchanged (backward compatible).
"""

import os
import tempfile

import pytest

from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
)
from praisonaiagents.tools.path_safety import is_within_root


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as root:
        real_root = os.path.realpath(root)
        os.makedirs(os.path.join(real_root, "sub"), exist_ok=True)
        yield real_root


@pytest.fixture
def manager(workspace):
    with tempfile.TemporaryDirectory() as tmp:
        mgr = PermissionManager(storage_dir=tmp, workspace_root=workspace)
        # Allow shell/write broadly so only the boundary gate can trigger asks.
        mgr.add_rule(
            PermissionRule(pattern="bash:*", action=PermissionAction.ALLOW, priority=1)
        )
        mgr.add_rule(
            PermissionRule(pattern="write:*", action=PermissionAction.ALLOW, priority=1)
        )
        yield mgr


class TestIsWithinRoot:
    def test_inside(self, workspace):
        assert is_within_root(os.path.join(workspace, "a.txt"), workspace)

    def test_root_itself(self, workspace):
        assert is_within_root(workspace, workspace)

    def test_outside_absolute(self, workspace):
        assert not is_within_root("/etc/hosts", workspace)

    def test_outside_traversal(self, workspace):
        assert not is_within_root(
            os.path.join(workspace, "..", "other"), workspace
        )

    def test_relative_inside(self, workspace):
        assert is_within_root("sub/file.txt", workspace)


class TestShellBoundary:
    def test_external_write_redirect_asks(self, manager):
        # Broad bash/write allow present, but writing outside root must ask.
        result = manager.check("bash:echo hi > /etc/evil.conf")
        assert result.needs_approval

    def test_external_path_arg_asks(self, manager):
        result = manager.check("bash:cat /etc/passwd")
        assert result.needs_approval

    def test_home_expansion_external_asks(self, manager):
        result = manager.check("bash:echo x > ~/.bashrc")
        assert result.needs_approval

    def test_in_workspace_write_allowed(self, manager, workspace):
        target = os.path.join(workspace, "out.txt")
        result = manager.check(f"bash:echo hi > {target}")
        assert result.is_allowed

    def test_in_workspace_relative_allowed(self, manager):
        result = manager.check("bash:cat ./sub/file.txt")
        assert result.is_allowed

    def test_plain_command_no_paths_allowed(self, manager):
        result = manager.check("bash:ls -la")
        assert result.is_allowed

    def test_external_dir_can_be_preauthorised(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="external_dir:/data/*",
                action=PermissionAction.ALLOW,
                priority=100,
            )
        )
        result = manager.check("bash:cat /data/input.csv")
        assert result.is_allowed

    def test_external_dir_can_be_denied(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="external_dir:*",
                action=PermissionAction.DENY,
                priority=100,
            )
        )
        assert manager.check("bash:cat /etc/passwd").is_denied

    def test_bare_relative_traversal_asks(self, manager):
        # Bare relative path that escapes via ``..`` (no leading ./ or ../).
        result = manager.check("bash:cat sub/../../../etc/passwd")
        assert result.needs_approval

    def test_joined_flag_path_asks(self, manager):
        # Path operand hidden behind a joined flag must still be gated.
        result = manager.check("bash:tool --config=/etc/app.conf")
        assert result.needs_approval

    def test_external_executable_path_asks(self, manager):
        # Running an executable outside the workspace must ask.
        result = manager.check("bash:/tmp/outside-tool")
        assert result.needs_approval

    def test_external_relative_executable_asks(self, manager):
        result = manager.check("bash:../../outside/tool.sh")
        assert result.needs_approval

    def test_bare_executable_name_allowed(self, manager):
        # PATH-resolved bare command name must not trigger a boundary prompt.
        result = manager.check("bash:ls")
        assert result.is_allowed


class TestFileToolBoundary:
    def test_external_path_asks(self, manager):
        res = manager.check_path_boundary("/etc/hosts")
        assert res is not None and res.needs_approval

    def test_in_workspace_returns_none(self, manager, workspace):
        assert manager.check_path_boundary(os.path.join(workspace, "a.txt")) is None


class TestBackwardCompatibility:
    def test_no_workspace_root_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PermissionManager(storage_dir=tmp)  # no workspace_root
            mgr.add_rule(
                PermissionRule(
                    pattern="bash:*", action=PermissionAction.ALLOW, priority=1
                )
            )
            mgr.add_rule(
                PermissionRule(
                    pattern="write:*", action=PermissionAction.ALLOW, priority=1
                )
            )
            # Without a workspace root, no external gate fires.
            assert mgr.check("bash:cat /etc/passwd").is_allowed
            assert mgr.check("bash:echo x > /etc/evil").is_allowed
            assert mgr.check_path_boundary("/etc/hosts") is None

    def test_deny_still_wins_over_boundary(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="bash:rm *", action=PermissionAction.DENY, priority=100
            )
        )
        # rm outside workspace: deny wins over the ask boundary gate.
        assert manager.check("bash:rm -rf /etc/other").is_denied
