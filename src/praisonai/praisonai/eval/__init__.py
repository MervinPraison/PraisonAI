"""Forwarding shim for :mod:`praisonai.eval`."""
from praisonai.cli._shim import alias_package

alias_package("praisonai.eval", "praisonaiagents.eval")
