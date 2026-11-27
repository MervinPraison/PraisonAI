"""Forwarding shim for :mod:`praisonai.memory`."""
from praisonai.cli._shim import alias_package

alias_package("praisonai.memory", "praisonaiagents.memory")
