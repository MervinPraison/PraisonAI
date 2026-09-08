"""Config tests must not read the developer's shell.

``ConfigResolver._load_env_config`` folds MODEL_NAME / OPENAI_MODEL_NAME and
friends into an "environment" layer. Exporting those is the normal way to use
this tool, so config tests were asserting against whoever ran them: seven were
red on this machine and green on CI, where nothing is exported. Machine-
dependent tests are worse than missing ones -- they train you to ignore a red
suite.

The ``isolated_config_env`` fixture scrubs them. This module keeps that list
honest by reading the resolver: a variable added there and not listed here
would silently reopen the leak.
"""

import ast
import os
from pathlib import Path

import pytest

from praisonai_code.cli.configuration import resolver as resolver_mod
from praisonai_code.cli.configuration.resolver import ConfigResolver

from .conftest import CONFIG_ENV_VARS


def _env_vars_read_by_load_env_config():
    """Env-var names read by ``_load_env_config``.

    Matches the ``("VAR_NAME", ["section", "key"])`` mapping shape and direct
    ``os.environ.get("VAR")`` calls. Deliberately not "every uppercase string
    in the function": the bare suffixes in ``env_var.endswith(("COLOR",
    "VERBOSE", "QUIET"))`` are not variables, and counting them would make this
    guard demand that the fixture scrub names that do not exist.
    """
    tree = ast.parse(Path(resolver_mod.__file__).read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_load_env_config"
    )
    names = set()
    for node in ast.walk(fn):
        # ("VAR", [...]) mapping entries
        if (isinstance(node, ast.Tuple) and node.elts
                and isinstance(node.elts[0], ast.Constant)
                and isinstance(node.elts[0].value, str)
                and len(node.elts) == 2
                and isinstance(node.elts[1], (ast.List, ast.Tuple))):
            names.add(node.elts[0].value)
        # os.environ.get("VAR") / os.environ["VAR"]
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.isupper()):
            names.add(node.args[0].value)
    return names


def test_the_fixture_covers_every_variable_the_resolver_reads():
    read = _env_vars_read_by_load_env_config()
    # Only names that look like env vars, not the config keys they map to.
    candidates = {n for n in read if n.isupper()}
    missing = sorted(candidates - set(CONFIG_ENV_VARS))
    assert not missing, (
        "ConfigResolver reads these and isolated_config_env does not scrub "
        f"them, so config tests will read the developer's shell: {missing}"
    )


def test_resolution_is_unaffected_by_an_exported_model(monkeypatch,
                                                       isolated_config_env,
                                                       tmp_path):
    """The regression itself: an exported model must not reach the resolver."""
    monkeypatch.setenv("MODEL_NAME", "some-exported-model")
    monkeypatch.setenv("OPENAI_MODEL_NAME", "another-exported-model")
    # The fixture ran first; re-setting them here proves the *test* controls
    # the environment rather than inheriting it, and that a test which wants
    # the variable can still have it.
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    config = ConfigResolver(cwd=tmp_path).resolve()
    assert "environment" in config.sources
    assert config.agent.model in (
        "some-exported-model", "another-exported-model",
    )


def test_without_the_export_there_is_no_environment_layer(isolated_config_env,
                                                          monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    config = ConfigResolver(cwd=tmp_path).resolve()
    assert config.sources == ["defaults"], (
        "an environment layer appeared with nothing exported -- the fixture "
        "is missing a variable the resolver reads"
    )
