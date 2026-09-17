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

# Read by ``_load_env_user_config`` (not ``_load_env_config``), so the AST guard
# in test_config_env_isolation.py does not police these. They stand in for the
# whole user-config layer: an exported ``PRAISONAI_CONFIG_CONTENT`` (inline blob)
# or ``PRAISONAI_CONFIG`` (explicit path) would suppress file discovery and feed
# the developer's own config into resolution -- the same machine-dependence the
# fixture exists to prevent. Kept in a separate tuple so the two guards stay
# distinct: one polices the environment layer, this covers the user-config layer.
CONFIG_USER_ENV_VARS = (
    "PRAISONAI_CONFIG_CONTENT",
    "PRAISONAI_CONFIG",
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

    ``_load_env_user_config`` reads PRAISONAI_CONFIG_CONTENT / PRAISONAI_CONFIG,
    which likewise override file discovery with the developer's own config, so
    they are scrubbed too.
    """
    for name in CONFIG_ENV_VARS + CONFIG_USER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
