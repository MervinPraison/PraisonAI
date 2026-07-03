"""Backward-compatibility shim for :mod:`praisonai.bots`."""
from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
from praisonai.cli._shim import alias_package

alias_package("praisonai.bots", "praisonai_bot.bots")
