"""Regression tests for issue #4167 defect 3: version-skewed wrapper install.

A new ``praisonai-code`` running against a ``praisonai`` wrapper that predates
``external_agent_catalog`` must report the wrapper as *too old* rather than
silently returning an empty catalog while ``check_dependencies`` reports OK.
"""

import pytest

from praisonai_code.cli.features.external_agents import (
    ExternalAgentsHandler,
    _resolve_catalog_fn,
)


@pytest.fixture
def old_wrapper(monkeypatch):
    """Wrapper importable but lacking ``external_agent_catalog`` (mixed-version)."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )

    def _raise_attr(module_name, attr):
        raise AttributeError(attr)

    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.get_wrapper_attr", _raise_attr
    )


@pytest.fixture
def wrapper_missing(monkeypatch):
    """Standalone install: praisonai wrapper NOT installed."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )


def test_old_wrapper_is_reported_as_old_not_as_empty(old_wrapper, monkeypatch):
    """An outdated wrapper must not look like 'you asked for a nonexistent agent'."""
    # find_spec must see praisonai.integrations so we reach the version check.
    monkeypatch.setattr(
        "importlib.util.find_spec", lambda name: object()
    )
    ok, msg = ExternalAgentsHandler().check_dependencies()
    assert not ok
    assert "too old" in msg.lower()


def test_old_wrapper_resolver_returns_error(old_wrapper):
    fn, error = _resolve_catalog_fn()
    assert fn is None
    assert error is not None and "too old" in error.lower()


def test_missing_wrapper_degrades_quietly(wrapper_missing):
    """No wrapper at all is not an error here: standalone stays usable."""
    fn, error = _resolve_catalog_fn()
    assert fn is None
    assert error is None
