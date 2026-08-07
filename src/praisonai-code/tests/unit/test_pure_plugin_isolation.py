"""Tests for the ``--pure`` / ``--no-plugins`` per-run isolation scoping.

These guard the contract that suppression is *ephemeral*: setting
``PRAISONAI_NO_PLUGINS`` for one invocation must never leak into a later
in-process command that did not ask for it.
"""

import os

from praisonai_code.cli.utils.env_utils import (
    NO_PLUGINS_ENV,
    scoped_no_plugins,
    scopes_no_plugins,
)


def _clear_env():
    os.environ.pop(NO_PLUGINS_ENV, None)


def test_scoped_no_plugins_sets_and_restores_when_unset():
    _clear_env()
    assert NO_PLUGINS_ENV not in os.environ
    with scoped_no_plugins(True):
        assert os.environ.get(NO_PLUGINS_ENV) == "1"
    # Removed again on exit — no leak.
    assert NO_PLUGINS_ENV not in os.environ


def test_scoped_no_plugins_restores_prior_value():
    os.environ[NO_PLUGINS_ENV] = "prior"
    try:
        with scoped_no_plugins(True):
            assert os.environ.get(NO_PLUGINS_ENV) == "1"
        assert os.environ.get(NO_PLUGINS_ENV) == "prior"
    finally:
        _clear_env()


def test_scoped_no_plugins_noop_when_false():
    _clear_env()
    with scoped_no_plugins(False):
        assert NO_PLUGINS_ENV not in os.environ
    assert NO_PLUGINS_ENV not in os.environ


def test_scoped_no_plugins_restores_on_exception():
    _clear_env()
    try:
        with scoped_no_plugins(True):
            assert os.environ.get(NO_PLUGINS_ENV) == "1"
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert NO_PLUGINS_ENV not in os.environ


def test_decorator_scopes_pure_kwarg_and_preserves_signature():
    import inspect

    _clear_env()

    @scopes_no_plugins
    def command(ctx=None, pure=False, model=None):
        return os.environ.get(NO_PLUGINS_ENV, "<unset>")

    # Signature is preserved so Typer still sees the real options.
    params = list(inspect.signature(command).parameters)
    assert params == ["ctx", "pure", "model"]

    # Suppression is active during the call and gone afterwards.
    assert command(pure=True) == "1"
    assert NO_PLUGINS_ENV not in os.environ

    # A subsequent call without --pure is unaffected (no leak).
    assert command(pure=False) == "<unset>"
    assert NO_PLUGINS_ENV not in os.environ
