"""
Tests for reusable command-prefix approval scopes (permissions/arity.py).

Verifies that approving a shell command with a persistent scope can derive a
reusable command-prefix glob (e.g. ``git status`` -> ``bash:git status *``)
instead of only matching the literal command, while remaining fully backward
compatible with literal approvals.
"""

import shutil
import tempfile

from praisonaiagents.permissions import PermissionManager, PermissionAction
from praisonaiagents.permissions.arity import prefix, derive_pattern


class TestCommandPrefix:
    """Tests for the command-arity prefix helper."""

    def test_empty_tokens(self):
        assert prefix([]) == ""

    def test_git_two_token_prefix(self):
        assert prefix(["git", "status", "-s"]) == "git status"

    def test_git_bare_stays_single_token(self):
        assert prefix(["git"]) == "git"

    def test_npm_run_two_token_prefix(self):
        assert prefix(["npm", "run", "build"]) == "npm run"

    def test_npm_non_run_two_token_prefix(self):
        assert prefix(["npm", "install", "lodash"]) == "npm install"

    def test_docker_compose_prefix(self):
        assert prefix(["docker", "compose", "up", "-d"]) == "docker compose"

    def test_unknown_command_single_token(self):
        assert prefix(["ls", "-la"]) == "ls"

    def test_unknown_command_bare(self):
        assert prefix(["cowsay"]) == "cowsay"

    def test_arity_capped_by_token_count(self):
        # "git" wants 2 tokens but only 1 present.
        assert prefix(["git"]) == "git"
        # "npm" wants 2 tokens; with 2 present keeps both.
        assert prefix(["npm", "run"]) == "npm run"

    def test_custom_arity_map(self):
        # Multi-word key requests a deeper prefix (3 tokens) than base "foo" (1).
        custom = {"foo bar": 3, "foo": 1}
        assert prefix(["foo", "bar", "baz"], custom) == "foo bar baz"
        assert prefix(["foo", "qux"], custom) == "foo"


class TestDerivePattern:
    """Tests for deriving reusable glob patterns from approval targets."""

    def test_bash_git_status(self):
        assert derive_pattern("bash:git status") == "bash:git status *"

    def test_bash_git_status_with_args(self):
        assert derive_pattern("bash:git status -s .") == "bash:git status *"

    def test_bash_npm_run(self):
        assert derive_pattern("bash:npm run build") == "bash:npm run *"

    def test_bash_ls(self):
        assert derive_pattern("bash:ls -la") == "bash:ls *"

    def test_shell_prefix_supported(self):
        assert derive_pattern("shell:git log") == "shell:git log *"

    def test_non_shell_target_unchanged(self):
        assert derive_pattern("read:/etc/hosts") == "read:/etc/hosts"
        assert derive_pattern("write:/tmp/x") == "write:/tmp/x"

    def test_existing_glob_respected(self):
        assert derive_pattern("bash:git *") == "bash:git *"
        assert derive_pattern("bash:rm -rf ?") == "bash:rm -rf ?"

    def test_empty_command_unchanged(self):
        assert derive_pattern("bash:") == "bash:"

    def test_bare_command_stays_literal(self):
        # A lone command with no subcommand must NOT become "<cmd> *" — that
        # would auto-approve every subcommand (e.g. bare git -> git push).
        assert derive_pattern("bash:git") == "bash:git"
        assert derive_pattern("bash:ls") == "bash:ls"
        assert derive_pattern("shell:cowsay") == "shell:cowsay"

    def test_shell_operators_not_generalised(self):
        # Compound commands must not be generalised — a globbed prefix would
        # swallow the second command into the reusable scope.
        assert (
            derive_pattern("bash:cd /tmp && rm -rf x")
            == "bash:cd /tmp && rm -rf x"
        )
        assert derive_pattern("bash:ls | grep foo") == "bash:ls | grep foo"
        assert derive_pattern("bash:echo hi; rm x") == "bash:echo hi; rm x"
        assert derive_pattern("bash:cat $(whoami)") == "bash:cat $(whoami)"
        assert derive_pattern("bash:ls > out.txt") == "bash:ls > out.txt"


class TestManagerReusableScope:
    """Tests for reusable-scope integration in PermissionManager.approve."""

    def setup_method(self):
        self.storage = tempfile.mkdtemp()
        self.manager = PermissionManager(storage_dir=self.storage)

    def teardown_method(self):
        shutil.rmtree(self.storage, ignore_errors=True)

    def test_literal_default_backward_compatible(self):
        # Default (no reusable_scope) stores literal — old behaviour.
        approval = self.manager.approve(
            "bash:git status", approved=True, scope="always"
        )
        assert approval.pattern == "bash:git status"
        # Literal only matches the exact command.
        assert self.manager.check("bash:git status").is_allowed is True
        assert self.manager.check("bash:git status -s").needs_approval is True

    def test_reusable_scope_generalises(self):
        approval = self.manager.approve(
            "bash:git status", approved=True, scope="always",
            reusable_scope=True,
        )
        assert approval.pattern == "bash:git status *"
        # Now trailing-arg variants are auto-allowed.
        assert self.manager.check("bash:git status").is_allowed is True
        assert self.manager.check("bash:git status -s").is_allowed is True
        assert self.manager.check("bash:git status .").is_allowed is True
        # But a different subcommand still asks.
        assert self.manager.check("bash:git commit").needs_approval is True

    def test_reusable_scope_not_applied_for_once(self):
        approval = self.manager.approve(
            "bash:git status", approved=True, scope="once",
            reusable_scope=True,
        )
        # once scope is transient; pattern stays literal.
        assert approval.pattern == "bash:git status"

    def test_explicit_pattern_overrides(self):
        approval = self.manager.approve(
            "bash:git status", approved=True, scope="always",
            reusable_scope=True, pattern="bash:git *",
        )
        assert approval.pattern == "bash:git *"

    def test_suggest_scope_pattern(self):
        assert (
            self.manager.suggest_scope_pattern("bash:npm run build")
            == "bash:npm run *"
        )
        assert (
            self.manager.suggest_scope_pattern("read:/etc/hosts")
            == "read:/etc/hosts"
        )

    def test_reusable_scope_non_shell_unchanged(self):
        approval = self.manager.approve(
            "read:/etc/hosts", approved=True, scope="always",
            reusable_scope=True,
        )
        assert approval.pattern == "read:/etc/hosts"

    def test_reusable_scope_persists(self):
        self.manager.approve(
            "bash:npm run build", approved=True, scope="always",
            reusable_scope=True,
        )
        # Reload from disk to confirm generalised pattern was persisted.
        reloaded = PermissionManager(storage_dir=self.storage)
        assert reloaded.check("bash:npm run test").is_allowed is True

    def test_reusable_scope_bare_command_not_broadened(self):
        # Approving a bare "git" must not auto-approve arbitrary subcommands.
        approval = self.manager.approve(
            "bash:git", approved=True, scope="always", reusable_scope=True,
        )
        assert approval.pattern == "bash:git"
        assert self.manager.check("bash:git").is_allowed is True
        assert self.manager.check("bash:git push").needs_approval is True

    def test_reusable_scope_compound_command_not_broadened(self):
        # A compound command stays literal; the second op is not auto-approved.
        approval = self.manager.approve(
            "bash:cd /tmp && rm -rf x", approved=True, scope="always",
            reusable_scope=True,
        )
        assert approval.pattern == "bash:cd /tmp && rm -rf x"
        assert self.manager.check("bash:cd /tmp && rm -rf y").needs_approval


class TestBarePrefixMatchScoping:
    """The "<prefix> *" bare-match fallback is scoped to shell patterns only."""

    def _approval(self, pattern, approved=True):
        from praisonaiagents.permissions.rules import PersistentApproval
        return PersistentApproval(
            pattern=pattern, approved=approved, scope="always"
        )

    def test_shell_prefix_matches_bare_target(self):
        appr = self._approval("bash:git status *")
        assert appr.matches("bash:git status") is True
        assert appr.matches("bash:git status -s") is True

    def test_non_shell_prefix_does_not_match_bare_target(self):
        # A user-authored non-shell "* " pattern keeps exact fnmatch semantics:
        # the bare target (without the trailing space+glob) must NOT match.
        appr = self._approval("read:/secret *")
        assert appr.matches("read:/secret") is False
        assert appr.matches("read:/secret file") is True
