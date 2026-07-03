"""Backward-compatibility shim for :mod:`praisonai.kanban`."""
from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
from praisonai.cli._shim import alias_package

alias_package("praisonai.kanban", "praisonai_bot.kanban")
