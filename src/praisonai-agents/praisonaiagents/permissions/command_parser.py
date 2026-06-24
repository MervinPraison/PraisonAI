"""
Shell command parser for command-aware permission matching.

Decomposes a shell command string into its constituent simple-commands,
handling compound operators (``&&``, ``||``, ``;``, ``|``), subshells and
command substitution (``$(...)`` / backticks). Each resulting operation
exposes its executable, arguments and redirection targets so the permission
engine can evaluate file-mutating operations regardless of where they appear
in a compound statement.

Design goals:
- Dependency-light: stdlib ``shlex`` plus a small hand-rolled splitter.
- Best-effort and conservative: on any parse failure we fall back to treating
  the whole command as a single operation (today's behaviour) so a rule is
  never silently weakened.
"""

import shlex
from dataclasses import dataclass, field
from typing import List


# Operators that separate simple-commands within a compound command.
_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")

# Redirection operators that truncate/overwrite or append to a file.
# These produce an additional ``write:<path>`` sub-target.
_WRITE_REDIRECTS = (">", ">>", ">|", "&>", "&>>")


@dataclass
class ShellOp:
    """A single simple-command extracted from a shell command line.

    Attributes:
        executable: The command name (e.g. ``rm``), or ``""`` if unknown.
        args: Positional/flag arguments following the executable.
        write_targets: Paths that are written/truncated via redirection.
    """

    executable: str = ""
    args: List[str] = field(default_factory=list)
    write_targets: List[str] = field(default_factory=list)

    @property
    def command_string(self) -> str:
        """Reconstruct an ``<exe> <args>`` string for glob matching."""
        parts = [self.executable] + self.args
        return " ".join(p for p in parts if p)


def _extract_substitutions(token: str) -> List[str]:
    """Extract inner commands from ``$(...)`` and backtick substitutions.

    Returns a list of inner command strings (without the surrounding syntax).
    Best-effort; handles simple, non-nested cases which cover the common
    evasion vectors.
    """
    inner: List[str] = []

    # $(...) substitutions
    start = 0
    while True:
        idx = token.find("$(", start)
        if idx == -1:
            break
        depth = 0
        end = -1
        for i in range(idx + 1, len(token)):
            ch = token[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            break
        inner.append(token[idx + 2:end])
        start = end + 1

    # `...` backtick substitutions
    parts = token.split("`")
    if len(parts) >= 3:
        # Odd-indexed segments are inside backticks.
        for i in range(1, len(parts), 2):
            if parts[i].strip():
                inner.append(parts[i])

    return inner


def _split_simple_commands(cmd: str) -> List[str]:
    """Split a command line into simple-command segments on shell separators.

    Respects single/double quotes so separators inside quotes are ignored.
    Subshell parentheses are stripped and their contents treated as segments.
    """
    segments: List[str] = []
    current = []
    i = 0
    n = len(cmd)
    quote = None

    def flush():
        seg = "".join(current).strip()
        if seg:
            segments.append(seg)
        current.clear()

    while i < n:
        ch = cmd[i]

        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue

        # Subshell grouping: treat parens as separators (strip them).
        if ch in ("(", ")"):
            flush()
            i += 1
            continue

        # Two-character separators first.
        two = cmd[i:i + 2]
        if two in ("&&", "||"):
            flush()
            i += 2
            continue

        if ch in (";", "|", "&", "\n"):
            flush()
            i += 1
            continue

        current.append(ch)
        i += 1

    flush()
    return segments


def _parse_segment(segment: str) -> List[ShellOp]:
    """Parse a single simple-command segment into ShellOp(s).

    May return multiple ops when the segment embeds command substitutions.
    """
    ops: List[ShellOp] = []

    # First, recurse into any command substitutions so e.g. ``$(rm -rf x)``
    # is evaluated as an ``rm`` operation.
    for inner in _extract_substitutions(segment):
        ops.extend(parse_command(inner))

    try:
        tokens = shlex.split(segment, comments=False, posix=True)
    except ValueError:
        # Unbalanced quotes etc. — conservative fallback: whole segment.
        tokens = segment.split()

    op = ShellOp()
    args: List[str] = []
    skip_next = False

    for idx, tok in enumerate(tokens):
        if skip_next:
            op.write_targets.append(tok)
            skip_next = False
            continue

        # Skip leading environment-variable assignments (FOO=bar cmd).
        if op.executable == "" and not args and "=" in tok and tok.split("=", 1)[0].isidentifier():
            continue

        matched_redirect = False
        for redir in sorted(_WRITE_REDIRECTS, key=len, reverse=True):
            if tok == redir:
                skip_next = True
                matched_redirect = True
                break
            if tok.startswith(redir) and len(tok) > len(redir):
                op.write_targets.append(tok[len(redir):])
                matched_redirect = True
                break
            # Forms like 2> or 1>> (fd-prefixed redirect).
            if redir.startswith(">"):
                stripped = tok.lstrip("0123456789")
                if stripped == redir and stripped != tok:
                    skip_next = True
                    matched_redirect = True
                    break
                if stripped.startswith(redir) and len(stripped) > len(redir) and stripped != tok:
                    op.write_targets.append(stripped[len(redir):])
                    matched_redirect = True
                    break
        if matched_redirect:
            continue

        # Ignore input redirects and their target.
        if tok == "<":
            skip_next = False
            continue

        if op.executable == "":
            op.executable = tok
        else:
            args.append(tok)

    op.args = args

    if op.executable or op.write_targets:
        ops.append(op)

    return ops


def parse_command(cmd: str) -> List[ShellOp]:
    """Parse a shell command string into a list of ShellOp operations.

    Args:
        cmd: The raw shell command (without the ``bash:``/``shell:`` prefix).

    Returns:
        A list of ShellOp. On parse failure, returns a single best-effort
        ShellOp wrapping the whole command so existing behaviour is preserved.
    """
    if not cmd or not cmd.strip():
        return []

    try:
        segments = _split_simple_commands(cmd)
        ops: List[ShellOp] = []
        for seg in segments:
            ops.extend(_parse_segment(seg))

        if not ops:
            # Nothing extracted — fall back to whole command.
            return [_fallback_op(cmd)]
        return ops
    except Exception:
        # Any unexpected failure must not weaken the rule: fall back.
        return [_fallback_op(cmd)]


def _fallback_op(cmd: str) -> ShellOp:
    """Build a single ShellOp representing the whole command (legacy path)."""
    tokens = cmd.split()
    if not tokens:
        return ShellOp()
    return ShellOp(executable=tokens[0], args=tokens[1:])
