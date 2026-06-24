"""
Tests for command-aware permission matching for shell tool calls.

Verifies that a ``deny`` rule for a file-mutating command (e.g. ``rm``) fires
regardless of where the command appears in a compound statement: ``&&``, ``;``,
pipes, subshells, command substitution and truncating redirections.
"""

import tempfile

import pytest

from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
)
from praisonaiagents.permissions.command_parser import parse_command


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = PermissionManager(storage_dir=tmp)
        yield mgr


def _add_deny_rm(mgr):
    mgr.add_rule(
        PermissionRule(
            pattern="bash:rm *",
            action=PermissionAction.DENY,
            description="Block rm commands",
            priority=100,
        )
    )


class TestCommandParser:
    def test_simple_command(self):
        ops = parse_command("rm -rf /tmp")
        assert len(ops) == 1
        assert ops[0].executable == "rm"
        assert ops[0].args == ["-rf", "/tmp"]

    def test_and_compound(self):
        ops = parse_command("cd /tmp && rm -rf x")
        execs = [op.executable for op in ops]
        assert "cd" in execs
        assert "rm" in execs

    def test_semicolon_sequence(self):
        ops = parse_command("ls; rm -rf x")
        execs = [op.executable for op in ops]
        assert "ls" in execs
        assert "rm" in execs

    def test_pipe(self):
        ops = parse_command("cat foo | rm x")
        execs = [op.executable for op in ops]
        assert "cat" in execs
        assert "rm" in execs

    def test_command_substitution(self):
        ops = parse_command("echo $(rm -rf x)")
        execs = [op.executable for op in ops]
        assert "rm" in execs

    def test_backtick_substitution(self):
        ops = parse_command("echo `rm -rf x`")
        execs = [op.executable for op in ops]
        assert "rm" in execs

    def test_subshell(self):
        ops = parse_command("(cd /tmp && rm -rf x)")
        execs = [op.executable for op in ops]
        assert "rm" in execs

    def test_truncating_redirect(self):
        ops = parse_command("cat foo > /etc/hosts")
        targets = [t for op in ops for t in op.write_targets]
        assert "/etc/hosts" in targets

    def test_append_redirect(self):
        ops = parse_command("echo x >> /etc/hosts")
        targets = [t for op in ops for t in op.write_targets]
        assert "/etc/hosts" in targets

    def test_env_assignment_prefix(self):
        ops = parse_command("FOO=bar rm -rf x")
        assert any(op.executable == "rm" for op in ops)

    def test_empty(self):
        assert parse_command("") == []
        assert parse_command("   ") == []

    def test_input_redirect_not_executable(self):
        # ``< /dev/null`` must not be mistaken for the executable.
        ops = parse_command("rm -rf x < /dev/null")
        assert any(op.executable == "rm" for op in ops)
        assert all(op.executable != "/dev/null" for op in ops)

    def test_leading_input_redirect(self):
        ops = parse_command("< /dev/null cat foo")
        assert any(op.executable == "cat" for op in ops)
        assert all(op.executable != "/dev/null" for op in ops)

    def test_fd_to_fd_redirect_not_write_target(self):
        # ``2>&1`` aliases a file descriptor; it must not become a write target.
        ops = parse_command("ls foo 2>&1")
        targets = [t for op in ops for t in op.write_targets]
        assert "&1" not in targets
        assert all(not t.startswith("&") for t in targets)

    def test_single_quoted_substitution_is_literal(self):
        # ``echo '$(rm -rf x)'`` is a literal string, not an rm operation.
        ops = parse_command("echo '$(rm -rf x)'")
        assert all(op.executable != "rm" for op in ops)

    def test_double_quoted_substitution_still_extracted(self):
        # Double quotes do not suppress command substitution.
        ops = parse_command('echo "$(rm -rf x)"')
        assert any(op.executable == "rm" for op in ops)


class TestCommandAwareDeny:
    def test_plain_rm_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:rm -rf /tmp").is_denied

    def test_and_compound_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:cd /tmp && rm -rf x").is_denied

    def test_semicolon_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:ls; rm -rf x").is_denied

    def test_pipe_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:cat foo | rm x").is_denied

    def test_command_substitution_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:echo $(rm -rf x)").is_denied

    def test_subshell_denied(self, manager):
        _add_deny_rm(manager)
        assert manager.check("bash:(cd /tmp && rm -rf x)").is_denied

    def test_shell_prefix_denied(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="shell:rm *",
                action=PermissionAction.DENY,
                description="Block rm commands (shell prefix)",
                priority=100,
            )
        )
        assert manager.check("shell:ls && rm -rf x").is_denied


class TestRedirectDeny:
    def test_write_redirect_denied(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="write:/etc/*",
                action=PermissionAction.DENY,
                description="Protect /etc",
                priority=100,
            )
        )
        assert manager.check("bash:cat foo > /etc/hosts").is_denied

    def test_fd_to_fd_redirect_not_denied_by_broad_write_rule(self, manager):
        # A broad write deny must not block harmless ``2>&1`` redirections.
        manager.add_rule(
            PermissionRule(
                pattern="bash:*", action=PermissionAction.ALLOW, priority=10
            )
        )
        manager.add_rule(
            PermissionRule(
                pattern="write:*",
                action=PermissionAction.DENY,
                description="Block all writes",
                priority=100,
            )
        )
        assert not manager.check("bash:ls foo 2>&1").is_denied


class TestBackwardCompatibility:
    def test_flat_glob_still_matches(self, manager):
        _add_deny_rm(manager)
        # Existing behaviour: rm at start of command still denied.
        assert manager.check("bash:rm file.txt").is_denied

    def test_unrelated_command_not_denied(self, manager):
        _add_deny_rm(manager)
        result = manager.check("bash:ls -la")
        assert not result.is_denied

    def test_allow_all_subops(self, manager):
        manager.add_rule(
            PermissionRule(
                pattern="bash:*",
                action=PermissionAction.ALLOW,
                priority=10,
            )
        )
        result = manager.check("bash:ls && cat foo")
        assert result.is_allowed

    def test_compound_with_one_denied_blocks_all(self, manager):
        manager.add_rule(
            PermissionRule(pattern="bash:*", action=PermissionAction.ALLOW, priority=10)
        )
        _add_deny_rm(manager)
        # rm deny (priority 100) must win over bash:* allow.
        assert manager.check("bash:ls && rm x").is_denied

    def test_non_shell_target_unchanged(self, manager):
        manager.add_rule(
            PermissionRule(pattern="read:*", action=PermissionAction.ALLOW, priority=10)
        )
        assert manager.check("read:file.txt").is_allowed

    def test_compound_with_one_ask_requires_approval(self, manager):
        manager.add_rule(
            PermissionRule(pattern="bash:*", action=PermissionAction.ALLOW, priority=10)
        )
        manager.add_rule(
            PermissionRule(
                pattern="bash:cat *",
                action=PermissionAction.ASK,
                description="Require approval for cat",
                priority=50,
            )
        )
        # deny -> ask -> allow precedence: ask sub-op wins over allow.
        assert manager.check("bash:ls && cat foo").needs_approval

    def test_legacy_flat_deny_on_compound_target_still_fires(self, manager):
        # A flat deny rule written against the full compound string must still
        # participate even when individual sub-operations would be allowed.
        manager.add_rule(
            PermissionRule(pattern="bash:*", action=PermissionAction.ALLOW, priority=10)
        )
        manager.add_rule(
            PermissionRule(
                pattern="bash:cd /tmp && rm *",
                action=PermissionAction.DENY,
                description="Legacy exact compound deny",
                priority=100,
            )
        )
        assert manager.check("bash:cd /tmp && rm x").is_denied
