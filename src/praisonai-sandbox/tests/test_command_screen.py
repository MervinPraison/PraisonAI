"""The command screen must see what the shell will run, where it will run.

Two gaps let a command reach a blocked path while the check reported success:

* the heredoc stripper was a bare regex, so ``<<'X'`` inside a comment, quotes
  or a herestring deleted the *executable* lines after it from the checked text;
* only words starting with ``/``, ``~`` or ``.`` were checked, and they were
  resolved against the host process's cwd -- not the sandbox directory the
  command runs in -- so ``ln -s ../.. hop; cat hop/<blocked>`` passed.
"""
import os

import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy
from praisonai_sandbox._shell import strip_heredoc_bodies
from praisonai_sandbox.subprocess import SubprocessSandbox


@pytest.mark.parametrize("command", [
    "# <<'A'\ncat /etc/passwd\nA",
    ": # <<'A'\ncat /etc/passwd\nA",
    "cat <<<'A'\ncat /etc/passwd\nA",
    "echo \"<<'A'\ncat /etc/passwd\nA\"",
    "echo '<<'A'\ncat /etc/passwd\nA'",
])
def test_lines_after_a_dead_heredoc_operator_stay_visible(command):
    assert "cat /etc/passwd" in strip_heredoc_bodies(command)


def test_a_real_quoted_heredoc_body_is_still_stripped():
    command = "cat > f.txt <<'EOF'\nmentions /etc/passwd\nEOF\necho done"
    stripped = strip_heredoc_bodies(command)
    assert "/etc/passwd" not in stripped
    assert "echo done" in stripped


@pytest.fixture
def layout(tmp_path):
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "key").write_text("TOPSECRET")
    work = tmp_path / "work"
    work.mkdir()
    policy = SecurityPolicy(allow_network=True, allow_subprocess=True,
                            blocked_paths=[str(secret_dir)])
    sandbox = SubprocessSandbox(SandboxConfig(security_policy=policy))
    sandbox._temp_dir = str(work)
    return sandbox, work, secret_dir


def _check(sandbox, cmd, cwd=None):
    policy = sandbox.config.security_policy
    if cwd is None:  # runs in the sandbox's own directory
        return sandbox._validate_command_against_policy(cmd, policy)
    return sandbox._validate_command_against_policy(cmd, policy, cwd)


def test_a_relative_climb_is_resolved_where_the_command_runs(layout):
    sandbox, _, _ = layout
    assert _check(sandbox, ["cat", "../secret/key"])


def test_a_symlink_made_earlier_is_followed(layout):
    sandbox, work, _ = layout
    os.symlink("..", work / "hop")
    assert _check(sandbox, ["cat", "hop/secret/key"])


def test_a_bare_word_inside_a_blocked_cwd_is_refused(layout):
    sandbox, _, secret_dir = layout
    assert _check(sandbox, ["cat", "key"], cwd=str(secret_dir))


@pytest.mark.parametrize("cmd", [
    ["ln", "-s", "/", "hop"],
    ["sh", "-c", "cd .. && cat secret/key"],
    ["sh", "-c", "echo x >../secret/key"],
    ["tool", "--out=../secret/key"],
])
def test_reaching_a_blocked_path_indirectly_is_refused(layout, cmd):
    sandbox, _, _ = layout
    assert _check(sandbox, cmd)


@pytest.mark.parametrize("cmd", [
    ["echo", "hello"],
    ["ls", "-la"],
    ["sh", "-c", "mkdir -p out && echo hi > out/a.txt"],
    ["python3", "-c", "print(1)"],
])
def test_ordinary_commands_still_pass(layout, cmd):
    sandbox, _, _ = layout
    assert _check(sandbox, cmd) is None


@pytest.mark.asyncio
async def test_symlink_then_read_does_not_return_the_secret(tmp_path):
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "key").write_text("TOPSECRET")
    policy = SecurityPolicy(allow_network=True, allow_subprocess=True,
                            blocked_paths=[str(secret_dir)])
    (tmp_path / "other").mkdir()
    sandbox = SubprocessSandbox(SandboxConfig(security_policy=policy))
    await sandbox.start()
    try:
        await sandbox.run_command(["ln", "-s", str(tmp_path / "other"), "hop"])
        result = await sandbox.run_command(["cat", "hop/../secret/key"])
        assert "TOPSECRET" not in (result.stdout or "")
        assert result.error
    finally:
        await sandbox.stop()
