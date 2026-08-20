"""Shared error formatting for CLI backends."""

from __future__ import annotations

import subprocess


def called_process_error_message(exc: subprocess.CalledProcessError) -> str:
    """Render a subprocess failure with its captured stderr.

    ``str(CalledProcessError)`` only reports the exit status; the CLI's actual
    diagnostic lives in ``exc.stderr`` (populated as ``str`` or ``bytes`` by
    each backend's ``_execute_subprocess``).
    """
    stderr = getattr(exc, "stderr", None)
    if stderr:
        try:
            text = stderr.decode() if isinstance(stderr, bytes) else str(stderr)
        except AttributeError:
            text = str(stderr)
        text = text.strip()
        if text:
            return text
    return str(exc)
