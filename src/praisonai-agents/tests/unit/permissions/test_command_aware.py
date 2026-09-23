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
from praisonaiagents.permissions.command_parser import (
    parse_command,
    is_mutating_executable,
    DIALECT_POWERSHELL,
    DIALECT_CMD,
)


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

    def test_posix_default_dialect_unchanged(self):
        # A backslash-only token is *not* a path under POSIX (byte-for-byte).
        ops = parse_command("Remove-Item C:\\Windows\\foo")
        assert all(op.dialect == "posix" for op in ops)
        assert ops[0].path_args == []


class TestPowerShellParser:
    def test_powershell_command_wrapper_unwrapped(self):
        ops = parse_command('powershell -Command "Remove-Item C:\\tmp\\x"')
        execs = [op.executable for op in ops]
        assert "Remove-Item" in execs
        rm = next(op for op in ops if op.executable == "Remove-Item")
        assert rm.dialect == DIALECT_POWERSHELL

    def test_pwsh_short_flag_unwrapped(self):
        ops = parse_command('pwsh -c "New-Item .\\out.txt"')
        assert any(op.executable == "New-Item" for op in ops)

    def test_cmd_wrapper_unwrapped(self):
        ops = parse_command('cmd /c "del C:\\tmp\\x"')
        exe = [op.executable for op in ops]
        assert "del" in exe
        assert all(op.dialect == DIALECT_CMD for op in ops if op.executable == "del")

    def test_powershell_pipeline(self):
        ops = parse_command(
            'powershell -Command "Get-Content a.txt | Set-Content b.txt"'
        )
        execs = [op.executable for op in ops]
        assert "Get-Content" in execs
        assert "Set-Content" in execs

    def test_windows_drive_path_is_path_arg(self):
        ops = parse_command('powershell -Command "Remove-Item C:\\tmp\\x"')
        rm = next(op for op in ops if op.executable == "Remove-Item")
        assert "C:\\tmp\\x" in rm.path_args

    def test_windows_relative_path_is_path_arg(self):
        ops = parse_command('powershell -Command "Set-Content .\\out.txt hi"')
        sc = next(op for op in ops if op.executable == "Set-Content")
        assert ".\\out.txt" in sc.path_args

    def test_mutating_executable_powershell(self):
        assert is_mutating_executable("Remove-Item", DIALECT_POWERSHELL)
        assert is_mutating_executable("out-file", DIALECT_POWERSHELL)
        assert not is_mutating_executable("Get-ChildItem", DIALECT_POWERSHELL)

    def test_mutating_executable_cmd(self):
        assert is_mutating_executable("del", DIALECT_CMD)
        assert is_mutating_executable("RMDIR", DIALECT_CMD)
        assert not is_mutating_executable("dir", DIALECT_CMD)

    def test_mutating_executable_posix_is_false(self):
        # POSIX keeps its path-based (executable-agnostic) boundary behaviour.
        assert not is_mutating_executable("Remove-Item")
        assert not is_mutating_executable("rm")

    def test_option_prefixed_powershell_wrapper_unwrapped(self):
        # Switches before -Command (``-NoProfile``) must not defeat unwrap.
        ops = parse_command(
            'powershell -NoProfile -Command "Remove-Item C:\\outside\\x"'
        )
        rm = next(op for op in ops if op.executable == "Remove-Item")
        assert rm.dialect == DIALECT_POWERSHELL
        assert "C:\\outside\\x" in rm.path_args

    def test_option_prefixed_cmd_wrapper_unwrapped(self):
        # ``cmd /d /c`` (switch before /c) must still unwrap the inner command.
        ops = parse_command('cmd /d /c "del C:\\outside\\x"')
        d = next(op for op in ops if op.executable == "del")
        assert d.dialect == DIALECT_CMD
        assert "C:\\outside\\x" in d.path_args

    def test_powershell_scriptblock_surfaces_cmdlet(self):
        # ``& { Remove-Item … }`` must not leave ``{`` as the executable.
        ops = parse_command(
            'powershell -Command "& { Remove-Item .\\protected.txt }"'
        )
        execs = [op.executable for op in ops]
        assert "Remove-Item" in execs
        assert "{" not in execs
        rm = next(op for op in ops if op.executable == "Remove-Item")
        assert ".\\protected.txt" in rm.path_args

    def test_powershell_bare_call_operator_surfaces_cmdlet(self):
        ops = parse_command('powershell -Command "& Remove-Item .\\x"')
        assert any(op.executable == "Remove-Item" for op in ops)

    def test_encoded_command_decoded_and_inspected(self):
        import base64

        inner = "Remove-Item C:\\outside\\x"
        payload = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        ops = parse_command(f"powershell -EncodedCommand {payload}")
        rm = next(op for op in ops if op.executable == "Remove-Item")
        assert rm.dialect == DIALECT_POWERSHELL
        assert "C:\\outside\\x" in rm.path_args

    def test_encoded_command_abbreviation_decoded(self):
        import base64

        inner = "New-Item .\\out.txt"
        payload = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        ops = parse_command(f"pwsh -e {payload}")
        assert any(op.executable == "New-Item" for op in ops)

    def test_undecodable_encoded_command_fails_closed(self):
        # An undecodable payload must stay an opaque wrapper op (exe preserved),
        # never expose the base64 token as a bogus executable.
        ops = parse_command("powershell -EncodedCommand not!valid!base64")
        assert ops[0].executable.lower() == "powershell"

    def test_powershell_script_file_not_misparsed(self):
        # No command flag: ``powershell script.ps1`` stays a normal (opaque) op
        # rather than treating the filename as a command flag operand.
        ops = parse_command("powershell script.ps1")
        assert ops[0].executable.lower() == "powershell"


class TestPowerShellBoundary:
    def test_external_powershell_mutation_asks(self):
        with tempfile.TemporaryDirectory() as workspace:
            with tempfile.TemporaryDirectory() as outside:
                mgr = PermissionManager(storage_dir=workspace, workspace_root=workspace)
                mgr.add_rule(
                    PermissionRule(
                        pattern="bash:*", action=PermissionAction.ALLOW, priority=10
                    )
                )
                target = (
                    f'bash:powershell -Command "Remove-Item {outside}\\\\secret.txt"'
                )
                result = mgr.check(target)
                assert result.needs_approval

    def test_in_workspace_powershell_mutation_allowed(self):
        with tempfile.TemporaryDirectory() as workspace:
            mgr = PermissionManager(storage_dir=workspace, workspace_root=workspace)
            mgr.add_rule(
                PermissionRule(
                    pattern="bash:*", action=PermissionAction.ALLOW, priority=10
                )
            )
            inside = f"{workspace}/note.txt"
            target = f'bash:powershell -Command "Set-Content {inside} hi"'
            result = mgr.check(target)
            assert result.is_allowed

    def test_option_prefixed_external_mutation_asks(self):
        # ``-NoProfile`` before -Command must not let the external write slip
        # past the boundary gate under a broad ``bash:*`` allow.
        with tempfile.TemporaryDirectory() as workspace:
            with tempfile.TemporaryDirectory() as outside:
                mgr = PermissionManager(
                    storage_dir=workspace, workspace_root=workspace
                )
                mgr.add_rule(
                    PermissionRule(
                        pattern="bash:*", action=PermissionAction.ALLOW, priority=10
                    )
                )
                target = (
                    "bash:powershell -NoProfile -Command "
                    f'"Remove-Item {outside}\\\\secret.txt"'
                )
                assert mgr.check(target).needs_approval

    def test_encoded_external_mutation_asks(self):
        # A base64 -EncodedCommand external mutation must be decoded and gated.
        import base64

        with tempfile.TemporaryDirectory() as workspace:
            with tempfile.TemporaryDirectory() as outside:
                mgr = PermissionManager(
                    storage_dir=workspace, workspace_root=workspace
                )
                mgr.add_rule(
                    PermissionRule(
                        pattern="bash:*", action=PermissionAction.ALLOW, priority=10
                    )
                )
                inner = f"Remove-Item {outside}\\secret.txt"
                payload = base64.b64encode(
                    inner.encode("utf-16-le")
                ).decode("ascii")
                target = f"bash:powershell -EncodedCommand {payload}"
                assert mgr.check(target).needs_approval

    def test_scriptblock_denied_cmdlet_still_blocked(self):
        # A cmdlet-specific deny must still fire when hidden in a scriptblock.
        with tempfile.TemporaryDirectory() as workspace:
            mgr = PermissionManager(storage_dir=workspace, workspace_root=workspace)
            mgr.add_rule(
                PermissionRule(
                    pattern="bash:*", action=PermissionAction.ALLOW, priority=10
                )
            )
            mgr.add_rule(
                PermissionRule(
                    pattern="bash:Remove-Item *",
                    action=PermissionAction.DENY,
                    description="Block Remove-Item",
                    priority=100,
                )
            )
            target = 'bash:powershell -Command "& { Remove-Item .\\x }"'
            assert mgr.check(target).is_denied


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
