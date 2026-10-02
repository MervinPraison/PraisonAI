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
_HOST_APP = "praisonai.integration.host_app"


@pytest.fixture
def reload_integration():
    """Reload ``praisonai.integration`` cleanly, restoring global state after.

    The tests here poke at import-time behaviour by dropping cached modules,
    so we snapshot and restore the affected ``sys.modules`` entries to avoid
    leaking a partially-loaded package into unrelated tests (which would break
    ``monkeypatch.setattr`` path resolution elsewhere).
    """
    tracked = (_GATEWAY_HOST, _PACKAGE, _HOST_APP)
    saved = {name: sys.modules.get(name) for name in tracked}

    def _reload():
        for name in (_GATEWAY_HOST, _HOST_APP, _PACKAGE):
            sys.modules.pop(name, None)
        return importlib.import_module(_PACKAGE)

    try:
        yield _reload
    finally:
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
            else:
                sys.modules.pop(name, None)
        importlib.import_module(_PACKAGE)


def test_import_does_not_load_gateway_host(reload_integration):
    """Importing the package leaves gateway_host unloaded."""
    reload_integration()
    assert _GATEWAY_HOST not in sys.modules


def test_host_app_symbols_are_eager(reload_integration):
    """host_app exports remain importable without touching gateway_host."""
    pkg = reload_integration()
    for symbol in (
        "build_host_app",
        "configure_host",
        "create_host_app",
        "is_legacy_host",
        "setup_bridges",
    ):
        assert hasattr(pkg, symbol)
    assert _GATEWAY_HOST not in sys.modules


def test_run_integrated_gateway_loads_on_access(reload_integration):
    """Accessing run_integrated_gateway lazily loads gateway_host on first use."""
    pkg = reload_integration()
    assert _GATEWAY_HOST not in sys.modules

    resolved = pkg.run_integrated_gateway
    assert resolved is not None
    assert _GATEWAY_HOST in sys.modules

    from praisonai.integration.gateway_host import run_integrated_gateway

    assert resolved is run_integrated_gateway


def test_unknown_attribute_raises_attribute_error(reload_integration):
    """__getattr__ preserves normal AttributeError for unknown names."""
    pkg = reload_integration()
    with pytest.raises(AttributeError):
        pkg.does_not_exist


def test_all_exports_unchanged(reload_integration):
    """__all__ still advertises the full public surface."""
    pkg = reload_integration()
    assert set(pkg.__all__) == {
        "build_host_app",
        "configure_host",
        "create_host_app",
        "is_legacy_host",
        "setup_bridges",
        "run_integrated_gateway",
    }
