"""Regression tests for persistence doctor backend resolution."""

import builtins
import sys
import types

import pytest

from praisonai.cli.features.persistence import (
    _detect_store_backend,
    _test_conversation_store,
)


def _install_resolver(monkeypatch, resolver):
    db_package = types.ModuleType("praisonai.db")
    db_package.__path__ = []
    adapter_module = types.ModuleType("praisonai.db.adapter")
    adapter_module.PraisonAIDB = resolver
    monkeypatch.setitem(sys.modules, "praisonai.db", db_package)
    monkeypatch.setitem(sys.modules, "praisonai.db.adapter", adapter_module)


def test_unknown_backend_uses_doctor_default(monkeypatch):
    class Resolver:
        def _detect_backend(self, url):
            raise ValueError(f"unknown backend for {url}")

    _install_resolver(monkeypatch, Resolver)

    assert _detect_store_backend("unknown://db", default="sqlite") == "sqlite"


def test_unexpected_resolver_error_is_not_masked(monkeypatch):
    class Resolver:
        def _detect_backend(self, url):
            raise RuntimeError("resolver failed")

    _install_resolver(monkeypatch, Resolver)

    with pytest.raises(RuntimeError, match="resolver failed"):
        _detect_store_backend("postgresql://db", default="sqlite")


def test_adapter_import_failure_is_reported_by_store_test(monkeypatch):
    original_import = builtins.__import__

    def fail_adapter_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "praisonai.db.adapter":
            raise ImportError("adapter unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_adapter_import)

    ok, detail = _test_conversation_store("postgresql://db")

    assert not ok
    assert "adapter unavailable" in detail
