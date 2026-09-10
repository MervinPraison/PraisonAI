"""Shared fixtures for the praisonai-code unit tests."""

import ast
import os
from pathlib import Path

import pytest

# Every environment variable ConfigResolver folds into its "environment" layer.
# Kept in sync with the resolver by test_config_env_isolation.py, which parses
# the resolver and fails if a new one appears that is not listed here.
CONFIG_ENV_VARS = (
    "MODEL_NAME",
    "OPENAI_MODEL_NAME",
    "PRAISONAI_MODEL",
    "PRAISONAI_PROVIDER",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "PRAISONAI_BASE_URL",
    "PRAISONAI_OUTPUT_FORMAT",
    "PRAISONAI_COLOR",
    "PRAISONAI_VERBOSE",
    "PRAISONAI_QUIET",
    "PRAISONAI_MANAGED_CONFIG_URL",
    "PRAISONAI_MANAGED_CONFIG_DIR",
    "PRAISONAI_MANAGED_CONFIG_TIMEOUT",
    "PRAISONAI_STRICT_CONFIG",
    "PRAISONAI_TELEMETRY",
)


@pytest.fixture
def isolated_config_env(monkeypatch):
    """Hide the developer's shell from ConfigResolver.

    ``_load_env_config`` folds MODEL_NAME / OPENAI_MODEL_NAME and friends into
    an "environment" layer. Anyone who exports those -- which is the normal way
    to use this tool -- made config tests assert against their own shell:
    ``config.sources`` gained an "environment" entry and the resolved model
    became whatever they had set. The tests passed or failed per machine, and
    on CI (where nothing is exported) the gap was invisible.
    """
    for name in CONFIG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
