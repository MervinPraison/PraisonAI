"""Forwarding shim for :mod:`praisonai.knowledge`."""
from praisonai.cli._shim import alias_package

alias_package("praisonai.knowledge", "praisonaiagents.knowledge")
