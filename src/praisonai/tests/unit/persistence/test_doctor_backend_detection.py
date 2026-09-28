"""Regression tests for persistence doctor backend resolution."""

import sys
import types

import pytest

from praisonai.cli.features.persistence import _detect_store_backend


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
