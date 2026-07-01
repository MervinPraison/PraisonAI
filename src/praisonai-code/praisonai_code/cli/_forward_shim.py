"""Temporary forward shims removed in C5 — configuration, session, and utils
now live in ``praisonai_code.cli``. Bot-channel feature modules remain under
``praisonai.cli.features`` and are reached via that package's ``__path__`` extension.
"""

from __future__ import annotations


def install() -> None:
    """No-op — forward shims no longer required after C5."""
