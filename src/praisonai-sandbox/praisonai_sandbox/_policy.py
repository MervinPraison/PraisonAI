"""SecurityPolicy screening shared by the local sandbox backends.

These are static checks on the text that is about to run. They are a safety
net, not isolation (see SECURITY.md); a backend that cannot keep a policy field
at all must refuse it rather than rely on a screen.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Optional

# Split a shell word into the paths it may name: `>/etc/x`, `--out=/etc/x`.
_PATH_SPLIT = re.compile(r"[\s<>|&;()=`'\"]+")
_SHELLS = {"sh", "bash", "dash", "zsh", "csh", "ksh", "cmd", "powershell"}


def _resolve(path: str, cwd: Optional[str] = None) -> str:
    path = os.path.expanduser(path)
    return os.path.realpath(os.path.join(cwd, path) if cwd else path)


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def path_violation(token: str, policy, cwd: Optional[str] = None,
                   roots: Iterable[str] = ()) -> Optional[str]:
    """Return an error when *token*, resolved where it will run, breaks the policy.

    A relative token is resolved against the directory the command runs in,
    not the host process's cwd, and symlinks are followed. Naming a directory
    that contains a blocked path (`cd /etc`, `ln -s / x`) is refused too:
    everything under it is reachable from there.
    """
    resolved = _resolve(token, cwd)
    for blocked in policy.blocked_paths or ():
        blocked_abs = _resolve(blocked)
        if _within(resolved, blocked_abs) or _within(blocked_abs, resolved):
            return f"Access to blocked path: {blocked}"
    if policy.allowed_paths:
        allowed = [_resolve(p) for p in policy.allowed_paths]
        allowed += [os.path.realpath(r) for r in roots if r]
        if not any(_within(resolved, a) for a in allowed):
            return f"Path not in allowlist: {token}"
    return None


def screen_command(cmd: List[str], policy, cwd: Optional[str] = None,
                   roots: Iterable[str] = ()) -> Optional[str]:
    """Return an error message when argv *cmd* violates *policy*.

    *cwd* is where the command will run; *roots* are directories the sandbox
    always owns (its temp dir), allowed even when allowed_paths is set.
    """
    if not cmd:
        return "Empty command"

    from ._shell import policy_scan_parts, strip_heredoc_bodies

    # A quoted heredoc body is file content, not a command.
    stripped = [strip_heredoc_bodies(c) for c in cmd]
    cmd_str = " ".join(stripped)
    for blocked in policy.blocked_commands:
        if blocked and blocked in cmd_str:
            return f"Blocked command pattern: {blocked}"

    if policy.allowed_commands:
        base_cmd = os.path.basename(cmd[0])
        allowed = {c.split()[0] for c in policy.allowed_commands}
        if base_cmd not in allowed and cmd[0] not in policy.allowed_commands:
            return f"Command not in allowlist: {base_cmd}"

    if not policy.allow_subprocess and os.path.basename(cmd[0]) in _SHELLS:
        return "Subprocess execution is disabled by security policy"

    # Every word is checked, not only ones starting with / ~ or . -- a relative
    # word resolves against cwd, and a symlink made earlier redirects it.
    for part in policy_scan_parts(stripped):
        for token in _PATH_SPLIT.split(part):
            error = token and path_violation(token, policy, cwd, roots)
            if error:
                return error
    return None
