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

Windows dialects (PowerShell / ``cmd``): a ``powershell -Command "…"`` /
``pwsh -c "…"`` / ``cmd /c "…"`` wrapper otherwise collapses to a single
opaque op, hiding the inner file-mutating cmdlet from the workspace-boundary
gate. Such wrappers are unwrapped and their inner command string is parsed so
the same boundary check that fires for POSIX mutations also fires on Windows.
POSIX parsing is byte-for-byte unchanged (the wrapper unwrap only triggers for
the ``powershell``/``pwsh``/``cmd`` executables).
"""

import base64
import binascii
import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional


# Operators that separate simple-commands within a compound command.
_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")

# Shell *parameter* expansion that bash resolves at runtime, invisibly to the
# static tokenizer. ``rm${IFS}-rf${IFS}/`` tokenizes as one opaque token here
# but bash word-splits it into ``rm -rf /`` when executed, so a broad allow
# rule could match while a specific ``rm -rf *`` deny never does. Likewise a
# ``${VAR}`` or bare ``$VAR`` (e.g. ``rm -rf $HOME``) expands to an unknown
# value at runtime that could evade a value-specific deny while matching a
# broad ``bash:*`` allow. Command substitution (``$(...)`` / backticks) is
# deliberately *not* matched here: it is decomposed and evaluated per-op by
# ``parse_command`` already, so a deny on the inner command still fires. The
# pattern only accepts ``${`` or ``$`` followed by an identifier char, so
# ``$(`` (command substitution) never matches. Only parameter expansion,
# which cannot be statically resolved, is treated as unverifiable.
_UNSAFE_EXPANSION_RE = re.compile(r"\$(?:\{|[A-Za-z_])")


def has_unresolvable_expansion(cmd: str) -> bool:
    """Return ``True`` if *cmd* contains parameter expansion we cannot resolve.

    Detects ``${...}`` parameter expansion and bare ``$VAR`` references
    (including ``$IFS`` word-splitting tricks), both resolved by bash at
    runtime and invisible to a static tokenizer, so they cannot be safely
    matched against deny rules. Command substitution (``$(...)``/backticks) is
    excluded because it is decomposed per-operation elsewhere. Callers should
    escalate matching commands to ``ASK`` rather than letting a broad allow
    rule short-circuit.
    """
    if not cmd:
        return False
    return _UNSAFE_EXPANSION_RE.search(cmd) is not None

# Redirection operators that truncate/overwrite or append to a file.
# These produce an additional ``write:<path>`` sub-target.
_WRITE_REDIRECTS = (">", ">>", ">|", "&>", "&>>")


# Supported shell dialects for parsing. ``posix`` is the default and unchanged
# path; ``powershell`` and ``cmd`` recognise Windows command shape.
DIALECT_POSIX = "posix"
DIALECT_POWERSHELL = "powershell"
DIALECT_CMD = "cmd"


# Wrapper executables whose quoted ``-Command``/``-c``/``/c`` argument carries an
# inner command string that must be parsed in the matching dialect so the inner
# cmdlet/built-in is gated rather than the opaque wrapper.
_POWERSHELL_WRAPPERS = ("powershell", "powershell.exe", "pwsh", "pwsh.exe")
_CMD_WRAPPERS = ("cmd", "cmd.exe")


# File-mutating PowerShell cmdlets, their common aliases, and ``cmd`` built-ins.
# Used by the permission engine's file-mutation classifier so the external-
# directory boundary check recognises Windows mutations the same way it does
# POSIX ones (``rm``/``cp``/``mv``/…). Matched case-insensitively.
_POWERSHELL_MUTATING = frozenset(
    {
        "remove-item",
        "new-item",
        "move-item",
        "copy-item",
        "rename-item",
        "set-content",
        "add-content",
        "clear-content",
        "out-file",
        # PowerShell aliases for the cmdlets above.
        "ri",
        "rd",
        "del",
        "erase",
        "ni",
        "mi",
        "move",
        "cpi",
        "copy",
        "cp",
        "rni",
        "ren",
        "sc",
        "ac",
        "rm",
        "mv",
    }
)

_CMD_MUTATING = frozenset(
    {
        "del",
        "erase",
        "rd",
        "rmdir",
        "md",
        "mkdir",
        "move",
        "copy",
        "xcopy",
        "ren",
        "rename",
    }
)


def is_mutating_executable(executable: str, dialect: str = DIALECT_POSIX) -> bool:
    """Return ``True`` if *executable* is a file-mutating command for *dialect*.

    POSIX callers keep their existing (executable-agnostic, path-based) boundary
    behaviour; this helper is provided so Windows dialects can recognise
    PowerShell cmdlets/aliases and ``cmd`` built-ins by name. Matching is
    case-insensitive and ignores any directory prefix on the executable.
    """
    if not executable:
        return False
    name = executable.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if dialect == DIALECT_POWERSHELL:
        return name in _POWERSHELL_MUTATING
    if dialect == DIALECT_CMD:
        return name in _CMD_MUTATING
    return False


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


# Drive-letter absolute path (``C:\x`` / ``C:/x``) or UNC share (``\\host\x``).
_WINDOWS_ABS_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _looks_like_windows_path(tok: str) -> bool:
    """Return ``True`` if *tok* is a Windows/PowerShell path shape.

    Recognises drive-letter absolutes (``C:\\x``), UNC shares (``\\\\host\\x``),
    explicit relatives (``.\\x``, ``..\\x``) and any bare token embedding a
    backslash separator, in addition to the POSIX shapes. Used only for
    ``powershell``/``cmd`` ops so POSIX boundary behaviour is unchanged.
    """
    if not tok:
        return False
    if _looks_like_path(tok):
        return True
    return (
        bool(_WINDOWS_ABS_RE.match(tok))
        or tok.startswith(".\\")
        or tok.startswith("..\\")
        or "\\" in tok
    )


def _extract_flag_path(tok: str) -> str:
    """Extract a path operand attached to a short flag (``-o/tmp/x``).

    Handles the ``getopt`` short-option form where the value is joined to the
    flag with no separator (e.g. ``-o/tmp/outside``, ``-I/usr/include``). The
    leading dashes and flag letters are stripped and the first embedded
    path-shaped segment (``/…``, ``~…``, ``$…``) is returned; otherwise ``""``.
    Long flags (``--flag=…``) are handled separately via ``=`` splitting.
    """
    if not tok.startswith("-") or tok.startswith("--"):
        return ""
    body = tok.lstrip("-")
    for i, ch in enumerate(body):
        if ch in ("/", "~", "$"):
            candidate = body[i:]
            if _looks_like_path(candidate):
                return candidate
            break
    return ""


@dataclass
class ShellOp:
    """A single simple-command extracted from a shell command line.

    Attributes:
        executable: The command name (e.g. ``rm``), or ``""`` if unknown.
        args: Positional/flag arguments following the executable.
        write_targets: Paths that are written/truncated via redirection.
        dialect: The shell dialect this op was parsed under (``posix`` by
            default; ``powershell``/``cmd`` for unwrapped Windows commands).
    """

    executable: str = ""
    args: List[str] = field(default_factory=list)
    write_targets: List[str] = field(default_factory=list)
    dialect: str = DIALECT_POSIX

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
        as joined flags (``--config=/etc/x``) or short-flag-attached
        (``-o/tmp/x``) are also unwrapped so the value is boundary-checked.
        Plain flags and non-path values are ignored.
        """
        # POSIX behaviour is unchanged; Windows dialects additionally recognise
        # drive-letter/UNC/backslash path shapes so cmdlet operands are gated.
        is_path = (
            _looks_like_path
            if self.dialect == DIALECT_POSIX
            else _looks_like_windows_path
        )
        paths: List[str] = []
        for tok in self.args:
            if not tok:
                continue
            # Flag forms can hide a path operand: ``--flag=<value>`` (split on
            # ``=``) or short getopt ``-o<value>`` (value joined to the flag).
            if tok.startswith("-"):
                if "=" in tok:
                    value = tok.split("=", 1)[1]
                    if value and is_path(value):
                        paths.append(value)
                    continue
                attached = _extract_flag_path(tok)
                if attached:
                    paths.append(attached)
                continue
            if is_path(tok):
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


def _strip_quotes(tok: str) -> str:
    """Strip a single pair of surrounding single/double quotes from *tok*."""
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
        return tok[1:-1]
    return tok


# Leading ``powershell``/``pwsh``/``cmd`` executable of a wrapper segment.
# Matched case-insensitively; an optional ``.exe`` suffix is tolerated. The
# switches and the command flag that follow are parsed separately (below) so
# option-prefixed forms such as ``powershell -NoProfile -Command "…"`` or
# ``cmd /d /c "…"`` are recognised, not just the flag-immediately-after form.
_WRAPPER_EXE_RE = re.compile(
    r"^\s*(?P<exe>powershell|pwsh|cmd)(?:\.exe)?\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# PowerShell command flags whose operand is the inner command string.
_PS_COMMAND_FLAGS = ("-command", "-c", "-encodedcommand", "-e", "-ec")
# ``cmd`` command flags whose operand is the inner command string.
_CMD_COMMAND_FLAGS = ("/c", "/k")
# PowerShell base64 flags whose operand is a UTF-16LE base64 payload.
_PS_ENCODED_FLAGS = ("-encodedcommand", "-e", "-ec")


def _decode_powershell_encoded(payload: str) -> Optional[str]:
    """Decode a PowerShell ``-EncodedCommand`` base64 UTF-16LE *payload*.

    Returns the decoded inner command string, or ``None`` if the payload is not
    valid base64 / UTF-16LE so the caller can fail closed (treat the wrapper as
    an opaque, un-inspectable op) rather than exposing the base64 token as a
    bogus executable that a deny rule can never match.
    """
    token = payload.strip().strip("'\"")
    if not token:
        return None
    try:
        raw = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        decoded = raw.decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    return decoded.strip() or None


# Leading PowerShell call-operator/scriptblock scaffolding (``& { … }`` /
# ``. { … }``) that hides the real cmdlet behind a ``{`` token when tokenized.
_PS_SCRIPTBLOCK_RE = re.compile(r"^\s*[&.]\s*\{(?P<body>.*)\}\s*$", re.DOTALL)


def _strip_powershell_scaffolding(inner: str) -> str:
    """Strip a leading call-operator + scriptblock wrapper from *inner*.

    PowerShell's ``& { <cmd> }`` / ``. { <cmd> }`` invocation would otherwise
    tokenize with ``{`` as the executable, demoting the real cmdlet to an
    argument and letting a command-specific deny slip through. Unwrap the
    scriptblock body so the inner cmdlet surfaces as the executable. Returns
    *inner* unchanged when no such wrapper is present.
    """
    stripped = inner.strip()
    match = _PS_SCRIPTBLOCK_RE.match(stripped)
    if match is not None:
        return match.group("body").strip()
    # Bare leading call operator (``& Remove-Item …``) without a scriptblock.
    if stripped[:1] in ("&", ".") and stripped[1:2].isspace():
        return stripped[1:].strip()
    return stripped


def _split_wrapper_flag(rest: str, dialect: str) -> Optional[tuple]:
    """Split a wrapper's post-executable *rest* into (flag, operand).

    Skips leading switches (``-NoProfile``, ``/d``, …) until the command flag
    (``-Command``/``-c``/``-EncodedCommand`` for PowerShell, ``/c``/``/k`` for
    ``cmd``) is found, then returns that flag plus the verbatim remainder as the
    inner command operand. Returns ``None`` if no command flag is present.
    """
    command_flags = (
        _CMD_COMMAND_FLAGS if dialect == DIALECT_CMD else _PS_COMMAND_FLAGS
    )
    remaining = rest
    # Walk whitespace-separated leading tokens; the command flag's operand is
    # everything after it (captured verbatim to preserve backslash paths).
    while remaining:
        stripped = remaining.lstrip()
        parts = stripped.split(None, 1)
        token = parts[0]
        if token.lower() in command_flags:
            operand = parts[1] if len(parts) > 1 else ""
            return token.lower(), operand
        # Not the command flag: skip this switch and continue. A bare
        # ``powershell script.ps1`` (no command flag) yields ``None`` so the
        # wrapper stays opaque (fail-closed) instead of misparsing a filename.
        if not token.startswith("-") and not token.startswith("/"):
            return None
        if len(parts) == 1:
            return None
        remaining = parts[1]
    return None


def _opaque_wrapper_op(segment: str, dialect: str) -> List[ShellOp]:
    """Fail-closed op for an un-inspectable wrapper (e.g. undecodable base64).

    Preserves the original ``powershell``/``pwsh``/``cmd`` executable so a
    command-specific deny/allow still applies to the wrapper itself, and no
    broad wildcard silently authorises an opaque payload.
    """
    return [_fallback_op(segment, dialect)]


def _unwrap_shell_wrapper(segment: str) -> Optional[List[ShellOp]]:
    """Return ops for the inner command of a ``powershell``/``cmd`` wrapper.

    Detects ``powershell -Command "…"`` / ``pwsh -c "…"`` / ``cmd /c "…"`` —
    including option-prefixed forms (``powershell -NoProfile -Command "…"`` /
    ``cmd /d /c "…"``), ``-EncodedCommand`` base64 payloads, and ``& { … }``
    scriptblock invocations — in the *raw* segment and parses the inner command
    string in the matching dialect so the inner cmdlet/built-in and its paths
    are gated rather than the opaque wrapper. Returns ``None`` when *segment* is
    not such a wrapper, so callers fall back to normal per-segment parsing.
    Detection is executable-name based, so a POSIX command never triggers this
    path.
    """
    match = _WRAPPER_EXE_RE.match(segment)
    if match is None:
        return None
    exe = match.group("exe").lower()
    dialect = DIALECT_CMD if exe == "cmd" else DIALECT_POWERSHELL

    split = _split_wrapper_flag(match.group("rest"), dialect)
    if split is None:
        return None
    flag, operand = split

    inner = _strip_quotes(operand.strip()).strip()
    if flag in _PS_ENCODED_FLAGS:
        # Base64 UTF-16LE payload: decode so the real cmdlet is inspected;
        # fail closed to an opaque wrapper op if it cannot be decoded.
        decoded = _decode_powershell_encoded(inner)
        if decoded is None:
            return _opaque_wrapper_op(segment, dialect)
        inner = decoded

    if not inner:
        return None

    if dialect == DIALECT_POWERSHELL:
        inner = _strip_powershell_scaffolding(inner)
        if not inner:
            return None

    return parse_command(inner, dialect=dialect)


def _parse_segment(segment: str, dialect: str = DIALECT_POSIX) -> List[ShellOp]:
    """Parse a single simple-command segment into ShellOp(s).

    May return multiple ops when the segment embeds command substitutions.
    """
    ops: List[ShellOp] = []

    # ``powershell -Command "…"`` / ``cmd /c "…"`` carries an inner command that
    # would otherwise be an opaque op. Unwrap from the *raw* segment (before
    # shlex) so the inner command — and its backslash paths — are preserved and
    # parsed in the matching dialect.
    wrapped = _unwrap_shell_wrapper(segment)
    if wrapped is not None:
        return wrapped

    # First, recurse into any command substitutions so e.g. ``$(rm -rf x)``
    # is evaluated as an ``rm`` operation.
    for inner in _extract_substitutions(segment):
        ops.extend(parse_command(inner, dialect=dialect))

    # POSIX tokenizes with ``posix=True`` (unchanged). Windows dialects use
    # ``posix=False`` so backslash path separators (``C:\tmp\x``) are preserved
    # rather than consumed as escape characters; surrounding quotes are then
    # stripped from each token.
    posix_mode = dialect == DIALECT_POSIX
    try:
        tokens = shlex.split(segment, comments=False, posix=posix_mode)
    except ValueError:
        # Unbalanced quotes etc. — conservative fallback: whole segment.
        tokens = segment.split()
    if not posix_mode:
        tokens = [_strip_quotes(t) for t in tokens]

    op = ShellOp(dialect=dialect)
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


def parse_command(cmd: str, *, dialect: str = DIALECT_POSIX) -> List[ShellOp]:
    """Parse a shell command string into a list of ShellOp operations.

    Args:
        cmd: The raw shell command (without the ``bash:``/``shell:`` prefix).
        dialect: The shell dialect to parse under — ``posix`` (default,
            byte-for-byte unchanged), ``powershell`` or ``cmd``. Statement
            separators (``;``, ``|``, ``&&``/``||``, ``&``) are shared across
            dialects; the dialect is recorded on each op and drives the
            file-mutation classifier for Windows cmdlets/built-ins. A
            ``powershell``/``pwsh``/``cmd`` wrapper is unwrapped and its inner
            command parsed in the matching dialect regardless of the requested
            *dialect*, so a POSIX gate still sees into a Windows wrapper.

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
            ops.extend(_parse_segment(seg, dialect))

        if not ops:
            # Nothing extracted — fall back to whole command.
            return [_fallback_op(cmd, dialect)]
        return ops
    except Exception:  # noqa: BLE001 - conservative: never weaken a rule on parse failure
        # Any unexpected failure must not weaken the rule: fall back.
        return [_fallback_op(cmd, dialect)]


def _fallback_op(cmd: str, dialect: str = DIALECT_POSIX) -> ShellOp:
    """Build a single ShellOp representing the whole command (legacy path)."""
    tokens = cmd.split()
    if not tokens:
        return ShellOp(dialect=dialect)
    return ShellOp(executable=tokens[0], args=tokens[1:], dialect=dialect)
