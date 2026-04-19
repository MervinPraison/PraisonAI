"""Inline shell substitution for skill bodies.

Supports two forms (Claude Code parity):

* Inline:   ``!`echo hello` ``
* Fenced:   ````! ... ``` ``

Safe-by-default: ``enabled=False`` replaces every block with a
``[shell execution disabled]`` marker so skills authored with shell
injection can be rendered deterministically without running arbitrary
commands. Hosts (CLI, UI) opt-in explicitly by passing ``enabled=True``.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional

_INLINE_RE = re.compile(r"!`([^`\n]+)`")
_FENCED_RE = re.compile(r"```!\s*\n(.*?)\n```", re.DOTALL)

_DISABLED_MARKER = "[shell execution disabled]"


def _run(cmd: str, shell: str, timeout: int, cwd: Optional[str]) -> str:
    try:
        shell_exe = ["bash", "-lc"] if shell != "powershell" else ["pwsh", "-Command"]
        proc = subprocess.run(
            [*shell_exe, cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        out = proc.stdout.strip()
        if proc.returncode != 0 and proc.stderr:
            out = f"{out}\n[stderr] {proc.stderr.strip()}".strip()
        return out
    except subprocess.TimeoutExpired:
        return f"[shell timeout after {timeout}s: {cmd}]"
    except FileNotFoundError:
        return f"[shell error: interpreter not found for shell={shell}]"
    except Exception as exc:  # pragma: no cover
        return f"[shell error: {exc}]"


def render_shell_blocks(
    body: str,
    enabled: bool = False,
    shell: str = "bash",
    timeout: int = 15,
    cwd: Optional[str] = None,
) -> str:
    """Render ``!`cmd` `` and ```` ```! `` blocks inside a skill body.

    Args:
        body: SKILL.md body (post-substitution).
        enabled: Master switch. When False, every block is replaced with
            ``[shell execution disabled]``. Defaults to False.
        shell: ``bash`` (default) or ``powershell``.
        timeout: Per-command timeout in seconds.
        cwd: Working directory for commands (typically the skill dir).

    Returns:
        Body with shell placeholders resolved.
    """
    if body is None:
        return ""

    if not enabled:
        out = _INLINE_RE.sub(_DISABLED_MARKER, body)
        out = _FENCED_RE.sub(_DISABLED_MARKER, out)
        return out

    def _inline(m: re.Match) -> str:
        return _run(m.group(1), shell, timeout, cwd)

    def _fenced(m: re.Match) -> str:
        return _run(m.group(1), shell, timeout, cwd)

    out = _INLINE_RE.sub(_inline, body)
    out = _FENCED_RE.sub(_fenced, out)
    return out
