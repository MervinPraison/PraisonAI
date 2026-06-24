"""Tests for shared per-command authorization across bot adapters.

Covers the privileged-command guard (e.g. /learn) that lets Slack and Discord
restrict privileged commands consistently with Telegram, without breaking the
permissive default when no policy is configured.
"""

from praisonai.bots._commands import (
    CommandAccessPolicy,
    build_command_access_policy,
)


def test_no_policy_is_permissive():
    policy = CommandAccessPolicy()
    assert policy.is_configured is False
    assert policy.can_run("anyone", "learn") is True
    assert policy.can_run("anyone", "status") is True
    assert policy.can_run("anyone", "help") is True


def test_admin_users_makes_learn_admin_only():
    policy = CommandAccessPolicy(admin_users={"admin"})
    assert policy.is_configured is True
    assert policy.can_run("admin", "learn") is True
    assert policy.can_run("user", "learn") is False
    # non-privileged commands remain available to regular users
    assert policy.can_run("user", "status") is True
    assert policy.can_run("user", "help") is True
    assert policy.can_run("user", "whoami") is True


def test_user_allowed_commands_can_grant_learn():
    policy = CommandAccessPolicy(user_allowed_commands={"learn", "status"})
    assert policy.can_run("user", "learn") is True
    assert policy.can_run("user", "status") is True
    assert policy.can_run("user", "model") is False


def test_user_allowed_commands_without_learn_denies_it():
    policy = CommandAccessPolicy(user_allowed_commands={"status"})
    assert policy.can_run("user", "learn") is False
    assert policy.can_run("user", "status") is True


def test_get_allowed_commands_excludes_privileged_for_regular_user():
    policy = CommandAccessPolicy(admin_users={"admin"})
    all_cmds = {"learn", "status", "help"}
    assert policy.get_allowed_commands("user", all_cmds) == {"status", "help"}
    assert policy.get_allowed_commands("admin", all_cmds) == all_cmds


def test_get_allowed_commands_permissive_when_unconfigured():
    policy = CommandAccessPolicy()
    all_cmds = {"learn", "status", "help"}
    assert policy.get_allowed_commands("user", all_cmds) == all_cmds


def test_builder_parses_comma_separated_admins():
    class Cfg:
        admin_users = "alice, bob"
        user_allowed_commands = None

    policy = build_command_access_policy(Cfg())
    assert policy.admin_users == {"alice", "bob"}
    assert policy.can_run("alice", "learn") is True
    assert policy.can_run("carol", "learn") is False


def test_builder_defaults_to_permissive():
    class Cfg:
        pass

    policy = build_command_access_policy(Cfg())
    assert policy.is_configured is False
    assert policy.can_run("anyone", "learn") is True
