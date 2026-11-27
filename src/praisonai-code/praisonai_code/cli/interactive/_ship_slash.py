"""Interactive ``/ship`` and ``/steward`` slash-command runner.

Delegates directly to ``python -m praisonai_code <ship|steward>`` so interactive
sessions inherit every standalone CLI flag, ``PRAISONAI_DISABLE_SHIP``, and the
never-merge guard without duplicating flag parsing.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Callable, Optional

_STEWARD_ONCE_NOTE = (
    "(ran one steward cycle; run 'praisonai steward' in a terminal for continuous watching)"
)


def run_ship_slash(
    cmd: str,
    args: str = "",
    *,
    cwd: Optional[str] = None,
    run: Callable = subprocess.run,
) -> str:
    """Run ``ship`` or ``steward`` from an interactive slash command and return output."""
    if cmd not in ("ship", "steward"):
        return f"Unsupported command: /{cmd}"
    try:
        tokens = shlex.split(args) if args else []
    except ValueError as exc:
        return f"Invalid arguments for /{cmd}: {exc}"

    added_once = False
    if cmd == "steward" and not any(t in ("--once", "--help", "-h") for t in tokens):
        tokens = [*tokens, "--once"]
        added_once = True

    try:
        proc = run(
            [sys.executable, "-m", "praisonai_code", cmd, *tokens],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return f"Failed to run /{cmd}: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parts = [p for p in (out, err) if p]
    text = "\n".join(parts) if parts else f"/{cmd} exited with status {proc.returncode}"
    if added_once and proc.returncode == 0:
        text = f"{text}\n{_STEWARD_ONCE_NOTE}"
    return text
