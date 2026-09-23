"""Regression tests for issue #3512.

Three wrapper-resident feature handlers -- ``eval``, ``persistence`` and
``background`` -- were unreachable code-side because the
``praisonai_code.cli.features.*`` bridge modules that their siblings received
during extraction were never created for them. These tests verify the bridges
resolve and re-export the expected wrapper symbols.
"""

import importlib.util

import pytest


def test_missing_feature_bridges_resolve():
    """All three bridge modules are importable code-side."""
    for name in ("eval", "persistence", "background"):
        spec = importlib.util.find_spec(f"praisonai_code.cli.features.{name}")
        assert spec is not None, f"bridge praisonai_code.cli.features.{name} missing"


def test_eval_bridge_exports():
    pytest.importorskip("praisonai")
    from praisonai_code.cli.features.eval import EvalHandler, handle_eval_command

    assert callable(handle_eval_command)
    assert EvalHandler is not None


def test_persistence_bridge_exports():
    pytest.importorskip("praisonai")
    from praisonai_code.cli.features.persistence import handle_persistence_command

    assert callable(handle_persistence_command)


def test_background_bridge_exports():
    pytest.importorskip("praisonai")
    from praisonai_code.cli.features.background import (
        BackgroundHandler,
        handle_background_command,
    )

    assert callable(handle_background_command)
    assert BackgroundHandler is not None
