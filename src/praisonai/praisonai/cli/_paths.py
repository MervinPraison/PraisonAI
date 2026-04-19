"""Canonical filesystem paths for PraisonAI user state.

Mirrors the conventions used by ``hermes-agent`` (``~/.hermes``) and
``openclaw`` (``~/.openclaw``): one user-home directory per tool, with
configurable overrides via environment variables, so ``bot.yaml`` and
``.env`` don't pollute whatever working directory the user happened to
run ``praisonai onboard`` from.

Layout::

    ~/.praisonai/
    ├── .env              # secrets (chmod 600) — managed by onboard
    ├── bot.yaml          # default bot / gateway config
    └── logs/             # daemon stdout / stderr (created by launchd helper)

Overrides (first match wins for each key):

* ``PRAISONAI_HOME``        — full path for the directory (e.g. Nix store)
* ``PRAISONAI_ENV_FILE``    — full path for the ``.env`` file
* ``PRAISONAI_BOT_CONFIG``  — full path for the default ``bot.yaml``
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "praison_home",
    "default_env_file",
    "default_bot_config_path",
    "resolve_bot_config_path",
]


def praison_home() -> Path:
    """Return the canonical PraisonAI home directory.

    Honours ``PRAISONAI_HOME`` so packaging systems (Nix, Docker) can
    relocate state. Defaults to ``~/.praisonai``.
    """
    override = os.environ.get("PRAISONAI_HOME")
    return Path(override).expanduser() if override else Path.home() / ".praisonai"


def default_env_file() -> Path:
    """Return the path to the canonical ``.env`` file."""
    override = os.environ.get("PRAISONAI_ENV_FILE")
    return Path(override).expanduser() if override else praison_home() / ".env"


def default_bot_config_path() -> Path:
    """Return the path where ``praisonai onboard`` writes ``bot.yaml``.

    Users can force a custom path with ``PRAISONAI_BOT_CONFIG``.
    """
    override = os.environ.get("PRAISONAI_BOT_CONFIG")
    return Path(override).expanduser() if override else praison_home() / "bot.yaml"


def resolve_bot_config_path(cli_value: str = "bot.yaml") -> str:
    """Resolve the bot config path for CLI commands with sensible fallback.

    Precedence:

    1. ``cli_value`` if it is not the sentinel ``"bot.yaml"`` (i.e. user
       passed an explicit ``--config X``).
    2. ``./bot.yaml`` if it exists in the current working directory
       (back-compat for projects that already keep bot.yaml checked in).
    3. ``~/.praisonai/bot.yaml`` (or ``PRAISONAI_BOT_CONFIG``) — the
       canonical location written by ``praisonai onboard``.
    4. Fall back to ``cli_value`` unchanged so existing error messages
       ("config not found at bot.yaml") keep working.
    """
    # (1) explicit override from the caller
    if cli_value and cli_value != "bot.yaml":
        return cli_value
    # (2) honour an existing cwd file (back-compat)
    cwd_path = Path.cwd() / "bot.yaml"
    if cwd_path.is_file():
        return str(cwd_path)
    # (3) canonical home location
    home_path = default_bot_config_path()
    if home_path.is_file():
        return str(home_path)
    # (4) give up — return the caller's value so their own error handling
    # surfaces a useful "not found" message.
    return cli_value
