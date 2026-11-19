"""Guard: built-in bot commands that change host state are admin-only.

Once an operator configures ``admin_users``, a regular chat user must not be
able to roll back files (/undo) or create scheduled automations (/blueprint,
/automations accept) any more than they can run /learn. Every built-in
command is classified here, so a new one fails until it is placed.
"""
import pytest

from praisonai_bot.bots._commands import CommandAccessPolicy, CommandRegistry

# Change files, skills or scheduled jobs on the host.
HOST_STATE_COMMANDS = {"learn", "undo", "blueprint", "automations"}
# Read-only, or scoped to the caller's own conversation.
SESSION_COMMANDS = {
    "help", "status", "new", "stop", "whoami", "model", "usage", "compress",
    "recap", "queue", "sessions", "resume", "retry", "reasoning", "tasks",
}


def test_every_builtin_command_is_classified():
    builtins = {
        name for name, meta in CommandRegistry()._commands.items() if meta.get("builtin")
    }
    assert builtins == HOST_STATE_COMMANDS | SESSION_COMMANDS


@pytest.mark.parametrize("command", sorted(HOST_STATE_COMMANDS))
def test_host_state_command_is_admin_only_once_configured(command):
    policy = CommandAccessPolicy(admin_users={"admin"})
    assert policy.can_run("admin", command) is True
    assert policy.can_run("user", command) is False
    assert command not in policy.get_allowed_commands("user", {command, "status"})


@pytest.mark.parametrize("command", sorted(HOST_STATE_COMMANDS))
def test_unconfigured_policy_stays_permissive(command):
    assert CommandAccessPolicy().can_run("anyone", command) is True


def test_explicit_user_grant_still_works():
    policy = CommandAccessPolicy(admin_users={"admin"}, user_allowed_commands={"undo"})
    assert policy.can_run("user", "undo") is True
