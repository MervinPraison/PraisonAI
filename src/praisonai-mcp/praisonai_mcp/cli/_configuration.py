"""Lazy config helpers from praisonai-code (optional co-install)."""

from __future__ import annotations

from praisonai_mcp._code_bridge import import_code_module


def get_config_loader():
    fn = import_code_module("praisonai_code.cli.configuration.loader").get_config_loader
    return fn()


def configuration_schema():
    return import_code_module("praisonai_code.cli.configuration.schema")


def configuration_paths():
    return import_code_module("praisonai_code.cli.configuration.paths")


def configuration_loader_helpers():
    return import_code_module("praisonai_code.cli.configuration.loader")
