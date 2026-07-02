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


def _looks_like_path(tok: str) -> bool:
    """Return ``True`` if *tok* is path-like enough to warrant a boundary check.

    Conservative but covers common escape forms: absolute (``/x``),
    home-relative (``~``), explicit relative (``./``, ``../``, ``..``),
    env-prefixed (``$VAR/…``) and any bare token that embeds a ``/`` (e.g.
    ``subdir/../../etc/passwd``). Plain flags/values without a path shape are
    ignored so non-path args never trigger a spurious prompt.
    """
    if not tok:
        return False
    return (
        tok.startswith("/")
        or tok.startswith("~")
        or tok.startswith("./")
        or tok.startswith("../")
        or tok == ".."
        or tok.startswith("$")
        or "/" in tok
    )


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
        parts = [self.executable, *self.args]
        return " ".join(p for p in parts if p)

    @property
    def path_args(self) -> List[str]:
        """Args that look like filesystem paths (for boundary checks).

        Returns path-like tokens for boundary evaluation. Covers absolute
        (``/x``), home-relative (``~``), parent/relative (``./``, ``../``),
        env-prefixed (``$VAR/…``) and bare traversal/relative paths that
        embed ``/`` (e.g. ``subdir/../../etc/passwd``). Path operands passed
        as joined flags (``--config=/etc/x``) are also unwrapped so the value
        is boundary-checked. Plain flags and non-path values are ignored.
        """
        paths: List[str] = []
        for tok in self.args:
            if not tok:
                continue
            # Joined-flag form: --flag=<value> / -o=<value>. Unwrap and check
            # the value component (a path operand can hide behind a flag).
            if tok.startswith("-"):
                if "=" in tok:
                    value = tok.split("=", 1)[1]
                    if value and _looks_like_path(value):
                        paths.append(value)
                continue
            if _looks_like_path(tok):
                paths.append(tok)
        return paths


def _extract_substitutions(token: str) -> List[str]:
    """Extract inner commands from ``$(...)`` and backtick substitutions.

    Returns a list of inner command strings (without the surrounding syntax).
    Best-effort; handles simple, non-nested cases which cover the common
    evasion vectors.
    """
    inner: List[str] = []

    # Mask single-quoted spans so substitutions inside them are treated as the
    # literals the shell would see (e.g. ``echo '$(rm -rf x)'`` is harmless).
    # Double quotes do *not* suppress substitution in the shell, so we leave
    # those spans intact.
    masked_chars = []
    in_single = False
    for ch in token:
        if ch == "'":
            in_single = not in_single
            masked_chars.append("\x00")
            continue
        masked_chars.append("\x00" if in_single else ch)
    masked = "".join(masked_chars)

    # $(...) substitutions
    start = 0
    while True:
        idx = masked.find("$(", start)
        if idx == -1:
            break
        depth = 0
        end = -1
        for i in range(idx + 1, len(masked)):
            ch = masked[i]
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
    parts = masked.split("`")
    if len(parts) >= 3:
        # Odd-indexed segments are inside backticks. Use original-text offsets
        # so the extracted command retains its real characters.
        offset = 0
        for i, part in enumerate(parts):
            seg_start = offset
            seg_end = offset + len(part)
            if i % 2 == 1 and part.strip():
                inner.append(token[seg_start:seg_end])
            offset = seg_end + 1  # account for the backtick delimiter

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
    skip_input_target = False

    for tok in tokens:
        if skip_next:
            op.write_targets.append(tok)
            skip_next = False
            continue

        if skip_input_target:
            skip_input_target = False
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
                    dest = stripped[len(redir):]
                    # Skip fd-to-fd redirections like ``2>&1`` (dest is ``&N``),
                    # which alias a file descriptor rather than writing a path.
                    if not dest.startswith("&"):
                        op.write_targets.append(dest)
                    matched_redirect = True
                    break
        if matched_redirect:
            continue

        # Ignore input redirects and their target (consume the next token so a
        # filename like ``< /dev/null`` is never mistaken for the executable).
        if tok in ("<", "<<", "<<<"):
            skip_input_target = True
            continue
        stripped_input = tok.lstrip("0123456789")
        if stripped_input in ("<", "<<", "<<<") and stripped_input != tok:
            skip_input_target = True
            continue
        if tok.startswith("<") or (
            stripped_input.startswith("<") and stripped_input != tok
        ):
            # Inline form like ``<file`` or ``<<<word`` — target is attached.
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
    except Exception:  # noqa: BLE001 - conservative: never weaken a rule on parse failure
        # Any unexpected failure must not weaken the rule: fall back.
        return [_fallback_op(cmd)]


def _fallback_op(cmd: str) -> ShellOp:
    """Build a single ShellOp representing the whole command (legacy path)."""
    tokens = cmd.split()
    if not tokens:
        return ShellOp()
    return ShellOp(executable=tokens[0], args=tokens[1:])
