"""Shared utilities for safe shell command handling across sandbox backends."""

import re
import shlex
from typing import List, Union


def build_argv(command: Union[str, List[str]], shell: bool = False) -> List[str]:
    """
    Safely build command argv with explicit shell control.
    
    Args:
        command: String command or list of arguments
        shell: If True, explicitly use shell. If False, parse safely without shell.
    
    Returns:
        List of command arguments safe for subprocess execution
        
    Security:
        - shell=False (default): No shell injection possible
        - shell=True: Caller explicitly opts into shell evaluation
    """
    if isinstance(command, str):
        if not shell:
            # Safe parse: convert string to argv without invoking shell
            return shlex.split(command)
        else:
            # Explicit shell: caller has opted in
            return ["sh", "-c", command]
    else:
        # List input
        cmd_list = list(command)
        if shell:
            # Quote each element when combining into shell command
            quoted_cmd = " ".join(shlex.quote(arg) for arg in cmd_list)
            return ["sh", "-c", quoted_cmd]
        else:
            # Direct argv execution - no shell
            return cmd_list


def policy_scan_parts(cmd: list) -> list:
    """Expand a `sh -c "..."` argv into the tokens a policy check should see.

    With shell=True an argv is ``["sh", "-c", "cat /etc/passwd"]``. A path scan
    that iterates argv sees one opaque string starting with "cat", so
    ``blocked_paths`` silently stops matching. Splitting the payload back out
    restores the check without changing how the command runs.
    """
    parts = list(cmd)
    for i, token in enumerate(cmd):
        if token == "-c" and i + 1 < len(cmd):
            try:
                parts.extend(shlex.split(cmd[i + 1]))
            except ValueError:
                parts.extend(cmd[i + 1].split())
    return parts


def strip_heredoc_bodies(command: str) -> str:
    """Remove ``<<'DELIM' ... DELIM`` bodies from a command before policy checks.

    A quoted heredoc body is never executed -- it is the literal bytes of a
    file. Scanning it as if it were a command means you cannot write a file
    that merely *mentions* a blocked pattern: saving a shell tutorial
    containing "rm -rf" was rejected as an attempt to run it, and a file whose
    text contained "/etc/passwd" was rejected as an attempt to read it.

    Only the quoted form (``<<'EOF'``) is stripped. An unquoted heredoc still
    undergoes shell expansion, so its contents can execute and must stay in
    scope for the checks.

    Only a live operator counts. ``<<'X'`` inside a comment, inside quotes or
    in a herestring (``<<<``) opens no heredoc, so the lines after it run; a
    bare regex stripped them too and hid them from the policy.
    """
    out, i, last, state = [], 0, 0, None
    while i < len(command):
        ch = command[i]
        if state == "#":
            state = None if ch == "\n" else state
        elif state:  # inside ', " or $'...'
            if ch == "\\" and state != "'":
                i += 1
            elif ch == state[-1]:
                state = None
        elif ch == "\\":
            i += 1
        elif ch in "'\"":
            state = "$'" if ch == "'" and command[i - 1:i] == "$" else ch
        elif ch == "#" and (i == 0 or command[i - 1] in " \t\n;|&("):
            state = "#"
        elif command.startswith("<<'", i) and command[i - 1:i] != "<":
            match = _HEREDOC.match(command, i)
            if match:
                out.append(command[last:i] + "<<'HEREDOC'")
                i = last = match.end()
                continue
        i += 1
    return "".join(out) + command[last:]


# The closing delimiter must stand alone on its line, as the shell requires.
_HEREDOC = re.compile(r"<<'([^'\n]+)'\n.*?\n\1(?=\n|$)", re.DOTALL)
