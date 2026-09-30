"""Regression tests for lazy ``gateway_host`` loading in ``praisonai.integration``.

Importing ``praisonai.integration`` must NOT force-load the
``praisonai.integration.gateway_host`` stack — only ``host_app`` symbols are
eager (what UI/dashboard presets need). ``run_integrated_gateway`` resolves
lazily on first attribute access via the package ``__getattr__``.

Guards against a future eager import silently undoing the startup improvement.
"""
import importlib
import sys

import pytest

_GATEWAY_HOST = "praisonai.integration.gateway_host"
_PACKAGE = "praisonai.integration"


def _reload_integration():
    """Drop cached integration modules and re-import the package cleanly."""
    for name in [_GATEWAY_HOST, _PACKAGE]:
        sys.modules.pop(name, None)
    return importlib.import_module(_PACKAGE)


def test_import_does_not_load_gateway_host():
    """Importing the package leaves gateway_host unloaded."""
    _reload_integration()
    assert _GATEWAY_HOST not in sys.modules


def test_host_app_symbols_are_eager():
    """host_app exports remain importable without touching gateway_host."""
    pkg = _reload_integration()
    for symbol in (
        "build_host_app",
        "configure_host",
        "create_host_app",
        "is_legacy_host",
        "setup_bridges",
    ):
        assert hasattr(pkg, symbol)
    assert _GATEWAY_HOST not in sys.modules


def test_run_integrated_gateway_loads_on_access():
    """Accessing run_integrated_gateway lazily loads gateway_host on first use."""
    pkg = _reload_integration()
    assert _GATEWAY_HOST not in sys.modules

    resolved = pkg.run_integrated_gateway
    assert resolved is not None
    assert _GATEWAY_HOST in sys.modules

    from praisonai.integration.gateway_host import run_integrated_gateway

    assert resolved is run_integrated_gateway


def test_unknown_attribute_raises_attribute_error():
    """__getattr__ preserves normal AttributeError for unknown names."""
    pkg = _reload_integration()
    with pytest.raises(AttributeError):
        pkg.does_not_exist


def test_all_exports_unchanged():
    """__all__ still advertises the full public surface."""
    pkg = _reload_integration()
    assert set(pkg.__all__) == {
        "build_host_app",
        "configure_host",
        "create_host_app",
        "is_legacy_host",
        "setup_bridges",
        "run_integrated_gateway",
    }
