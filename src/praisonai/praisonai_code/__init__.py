"""praisonai_code — agentic terminal CLI package.

This package hosts the agentic terminal product extracted from the
``praisonai`` wrapper (see parent issue #2512). During the incremental
C0–C6 migration this package is developed inside ``src/praisonai`` so it
remains importable via the existing editable install; a standalone
``src/praisonai-code`` distribution is wired up in a later step.

Only agentic (non bot-channel) command modules live here. Bot-channel
commands (gateway, bot, onboard, pairing, identity, kanban, mint_link,
claw, dashboard) remain in ``praisonai.cli.commands``.
"""

__all__ = ["__version__"]

try:  # pragma: no cover - version resolution is best-effort during migration
    from praisonai.version import __version__
except Exception:  # pragma: no cover
    __version__ = "0.0.0"
