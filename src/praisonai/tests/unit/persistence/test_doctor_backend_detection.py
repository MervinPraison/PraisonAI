"""Regression tests for persistence doctor backend resolution."""

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


def _install_failing_adapter_import(monkeypatch, exc):
    class _BlockingFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "praisonai.db.adapter":
                raise exc
            return None  # noqa: RET501, PLR1711 - module finder protocol

    monkeypatch.delitem(sys.modules, "praisonai.db.adapter", raising=False)
    finder = _BlockingFinder()
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])


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


def test_adapter_import_failure_is_not_masked(monkeypatch):
    _install_failing_adapter_import(monkeypatch, ImportError("adapter unavailable"))

    with pytest.raises(ImportError, match="adapter unavailable"):
        _detect_store_backend("postgresql://db", default="sqlite")


def test_store_test_reports_adapter_import_failure(monkeypatch):
    _install_failing_adapter_import(monkeypatch, ImportError("adapter unavailable"))

    success, message = _test_conversation_store("postgresql://db")

    assert success is False
    assert "adapter unavailable" in message
