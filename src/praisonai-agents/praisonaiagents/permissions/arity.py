"""
Command-arity inference for reusable permission-prefix scopes.

When a user approves a shell command with a persistent scope (``session`` or
``always``), recording the *literal* command string means only that exact
command is auto-allowed next time. Approving ``git status`` will not match a
later ``git status -s`` or ``git status .`` — producing approval fatigue.

This module derives a *reusable command prefix* from a small, extensible
command-arity table so that, for example:

* ``git status``         -> ``git status``  (prefix) -> pattern ``bash:git status *``
* ``npm run build``      -> ``npm run``      (prefix) -> pattern ``bash:npm run *``
* ``docker compose up``  -> ``docker compose`` (prefix) -> pattern ``bash:docker compose *``
* ``ls -la``             -> ``ls``           (prefix) -> pattern ``bash:ls *``

Unknown commands fall back to a conservative single-token prefix, so a bare
``git`` never over-generalises to *all* git subcommands.

The table is intentionally small and additive; it can be extended without
touching the matching hot path (``fnmatch`` already handles the ``*`` suffix).
"""

from typing import Dict, List, Optional

# Command -> number of leading tokens to KEEP as the reusable prefix.
#
# The value is how many leading tokens make up the "meaningful" command that
# should be generalised (the remainder becomes ``*``). For example ``git`` -> 2
# keeps ``git status`` from ``git status -s``. Multi-word keys (e.g.
# ``"npm run"``) allow a subcommand to request a deeper prefix than its base
# command; the longest matching key wins. Unknown commands default to keeping a
# single leading token, so a bare ``git`` never over-generalises to all git.
ARITY: Dict[str, int] = {
    # Version control
    "git": 2,          # git status -s      -> git status *
    "gh": 2,           # gh pr create       -> gh pr *
    "hg": 2,
    "svn": 2,
    # Package managers / build tools
    "npm": 2,          # npm run build      -> npm run *
    "yarn": 2,
    "pnpm": 2,
    "pip": 2,          # pip install x      -> pip install *
    "cargo": 2,        # cargo run --bin x  -> cargo run *
    "go": 2,           # go test ./...      -> go test *
    "poetry": 2,
    "uv": 2,
    "make": 2,
    # Containers / orchestration
    "docker": 2,       # docker compose up  -> docker compose *
    "docker compose": 2,  # docker compose up -d -> docker compose *
    "kubectl": 2,      # kubectl get pods   -> kubectl get *
    "helm": 2,
    # Python tooling
    "python": 2,       # python -m pytest   -> python -m *
    "python3": 2,
    "pytest": 1,       # pytest tests/      -> pytest *
    "ruff": 2,         # ruff check .       -> ruff check *
    # System / misc
    "apt": 2,
    "apt-get": 2,
    "brew": 2,
    "systemctl": 2,
}


def prefix(tokens: List[str], arity_map: Optional[Dict[str, int]] = None) -> str:
    """Return the longest meaningful command prefix for ``tokens``.

    Args:
        tokens: The command split into whitespace-delimited tokens
            (e.g. ``["git", "status", "-s"]``).
        arity_map: Optional override for the arity table (defaults to
            :data:`ARITY`).

    Returns:
        The meaningful command prefix as a single space-joined string. For an
        empty ``tokens`` list an empty string is returned.

    Examples:
        >>> prefix(["git", "status", "-s"])
        'git status'
        >>> prefix(["npm", "run", "build"])
        'npm run'
        >>> prefix(["ls", "-la"])
        'ls'
        >>> prefix(["git"])
        'git'
    """
    if not tokens:
        return ""

    table = ARITY if arity_map is None else arity_map

    # Try the longest multi-word keys first so "docker compose" wins over
    # "docker". The matched value is the number of leading tokens to keep.
    key_word_counts = sorted(
        {len(k.split()) for k in table}, reverse=True
    )
    for n in key_word_counts:
        if n > len(tokens):
            continue
        candidate = " ".join(tokens[:n])
        if candidate in table:
            keep = min(table[candidate], len(tokens))
            return " ".join(tokens[:keep])

    # Unknown command: keep only the first token (conservative default) so a
    # bare command never over-generalises to all of its subcommands.
    return tokens[0]


def derive_pattern(
    target: str, arity_map: Optional[Dict[str, int]] = None
) -> str:
    """Derive a reusable glob pattern for a shell approval ``target``.

    Only ``bash:``/``shell:`` targets are generalised; any other target (or one
    that already contains a glob) is returned unchanged so callers can safely
    apply this unconditionally.

    Args:
        target: The approval target, e.g. ``"bash:git status -s"``.
        arity_map: Optional override for the arity table.

    Returns:
        A reusable pattern such as ``"bash:git status *"``. The target is
        returned **unchanged** when it is not a shell target, is empty, already
        contains ``*``/``?`` glob characters, contains a shell control operator
        (``&&``, ``|``, ``;``, ``$(...)`` etc.), or is a bare single-token
        command (so a lone ``git`` never becomes ``git *``).

    Examples:
        >>> derive_pattern("bash:git status")
        'bash:git status *'
        >>> derive_pattern("bash:npm run build")
        'bash:npm run *'
        >>> derive_pattern("bash:git")            # bare command stays literal
        'bash:git'
        >>> derive_pattern("bash:cd /tmp && rm x")  # operator -> literal
        'bash:cd /tmp && rm x'
        >>> derive_pattern("read:/etc/hosts")
        'read:/etc/hosts'
    """
    shell_prefixes = ("bash:", "shell:")
    matched = next((p for p in shell_prefixes if target.startswith(p)), None)
    if matched is None:
        return target

    command = target[len(matched):].strip()
    if not command:
        return target

    # If the user already provided a glob, respect it verbatim.
    if "*" in command or "?" in command:
        return target

    # Shell control operators / substitutions. If the command contains any of
    # these, a globbed prefix would silently swallow a *second* command into
    # the reusable scope (e.g. ``cd /tmp && rm -rf x`` -> ``cd *``). Refuse to
    # generalise such commands and keep the literal target instead.
    _SHELL_OPERATORS = ("&&", "||", "|", ";", "&", "$(", "`", ">", "<", "\n")
    if any(op in command for op in _SHELL_OPERATORS):
        return target

    tokens = command.split()
    cmd_prefix = prefix(tokens, arity_map)
    if not cmd_prefix:
        return target

    # A bare single-token command (e.g. ``git`` with no subcommand) must not be
    # generalised to ``git *`` — that would auto-approve every subcommand,
    # violating the documented conservative contract. Only generalise when the
    # prefix is genuinely a prefix (i.e. there is at least one trailing token to
    # replace with ``*``); a lone token that already equals the full command has
    # nothing to generalise and is kept literal.
    if len(cmd_prefix.split()) == 1 and cmd_prefix == command:
        return target

    return f"{matched}{cmd_prefix} *"
