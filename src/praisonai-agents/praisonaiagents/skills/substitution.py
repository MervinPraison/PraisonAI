"""Skill body substitution engine.

Replaces `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N`, `${PRAISON_SKILL_DIR}`, and
`${PRAISON_SESSION_ID}` placeholders inside a SKILL.md body before it is
sent to the LLM.

Compatible aliases: `${CLAUDE_SKILL_DIR}` and `${CLAUDE_SESSION_ID}` mirror
the Claude Code variables so existing Claude Code skills work unchanged.

This module is pure Python and has no optional dependencies.
"""

from __future__ import annotations

import re
import shlex
from typing import Optional

_INDEXED_ARG_RE = re.compile(r"\$ARGUMENTS\[(\d+)\]")
_SHORT_ARG_RE = re.compile(r"(?<![A-Za-z0-9_])\$(\d+)\b")


def _parse_args(raw_args: str) -> list[str]:
    """Parse raw argument string using shell-like quoting.

    Example: `"hello world" foo` -> ["hello world", "foo"].
    Falls back to whitespace split on parse errors.
    """
    if not raw_args:
        return []
    try:
        return shlex.split(raw_args, posix=True)
    except ValueError:
        return raw_args.split()


def render_skill_body(
    body: str,
    raw_args: str = "",
    skill_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Render a SKILL.md body with placeholders substituted.

    Args:
        body: The markdown body (post-frontmatter) of a SKILL.md file.
        raw_args: The raw argument string after the skill name (e.g. when a
            user types ``/deploy staging prod``, ``raw_args="staging prod"``).
        skill_dir: Absolute path to the skill's directory.
        session_id: Current session identifier for logging/correlation.

    Returns:
        Rendered body ready to feed to the LLM.
    """
    if body is None:
        return ""

    args = _parse_args(raw_args)

    had_any_placeholder = (
        "$ARGUMENTS" in body
        or _INDEXED_ARG_RE.search(body) is not None
        or _SHORT_ARG_RE.search(body) is not None
    )

    # 1) Indexed arguments: $ARGUMENTS[N]
    def _indexed(m: re.Match) -> str:
        idx = int(m.group(1))
        return args[idx] if 0 <= idx < len(args) else ""

    out = _INDEXED_ARG_RE.sub(_indexed, body)

    # 2) Shorthand: $0, $1, ...  (not $ARGUMENTS)
    def _short(m: re.Match) -> str:
        idx = int(m.group(1))
        return args[idx] if 0 <= idx < len(args) else ""

    out = _SHORT_ARG_RE.sub(_short, out)

    # 3) Context variables (both PRAISON_ and CLAUDE_ aliases)
    replacements = {
        "${PRAISON_SKILL_DIR}": skill_dir or "",
        "${PRAISON_SESSION_ID}": session_id or "",
        "${CLAUDE_SKILL_DIR}": skill_dir or "",
        "${CLAUDE_SESSION_ID}": session_id or "",
    }
    for ph, val in replacements.items():
        out = out.replace(ph, val)

    # 4) Full $ARGUMENTS expansion
    if "$ARGUMENTS" in out:
        out = out.replace("$ARGUMENTS", raw_args)
    elif raw_args and not had_any_placeholder:
        # Footer fallback so caller still sees the input (Claude Code parity)
        out = f"{out.rstrip()}\n\nARGUMENTS: {raw_args}"

    return out
