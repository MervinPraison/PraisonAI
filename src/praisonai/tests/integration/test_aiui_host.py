"""Integration tests for PraisonAI ↔ PraisonAIUI host bootstrap (Pattern B)."""

from __future__ import annotations

import importlib
import os
import time

import pytest


pytest.importorskip("praisonaiui")


class TestHostAppBootstrap:
    def test_is_legacy_host_env(self, monkeypatch):
        from praisonai.integration.host_app import is_legacy_host

        monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)
        assert is_legacy_host() is False

        monkeypatch.setenv("PRAISONAI_HOST_LEGACY", "1")
        assert is_legacy_host() is True

    def test_configure_host_sets_provider(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)

        import praisonaiui.server as srv
        from praisonai.integration import host_app
        from praisonaiui.providers import PraisonAIProvider

        importlib.reload(host_app)
        host_app._CONFIGURED = False
        srv._provider = None

        seen = []
        monkeypatch.setattr(srv, "set_provider", lambda p: seen.append(p))

        host_app.configure_host(
            title="Test Host",
            pages=["chat"],
            agent_kwargs={"name": "test", "instructions": "test", "llm": "gpt-4o-mini"},
        )

        assert len(seen) == 1
        assert isinstance(seen[0], PraisonAIProvider)
        assert srv.get_datastore() is not None

    def test_legacy_skips_provider(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_HOST_LEGACY", "true")

        import praisonaiui.server as srv
        from praisonai.integration import host_app

        importlib.reload(host_app)
        host_app._CONFIGURED = False

        seen = []

        def _track(provider):
            seen.append(provider)

        monkeypatch.setattr(srv, "set_provider", _track)

        host_app.configure_host(pages=["chat"])
        assert seen == []

    def test_build_host_app_returns_starlette(self, monkeypatch):
        monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)

        from praisonai.integration import host_app

        importlib.reload(host_app)
        host_app._CONFIGURED = False

        app = host_app.build_host_app(pages=["chat"])
        assert app is not None
        assert hasattr(app, "routes")

    def test_host_import_performance(self):
        start = time.perf_counter()
        import praisonai.integration.host_app  # noqa: F401

        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 2000, f"host_app import took {elapsed_ms:.0f}ms"

    def test_hooks_query_bridge(self):
        from praisonai.integration.bridges.hooks_query import list_hooks_for_api

        hooks = list_hooks_for_api()
        assert isinstance(hooks, list)


class TestDefaultAppsLoad:
    @pytest.mark.parametrize(
        "module_path",
        [
            "praisonai.ui_chat.default_app",
            "praisonai.ui_dashboard.default_app",
            "praisonai.claw.default_app",
            "praisonai.ui_bot.default_app",
            "praisonai.ui_agents.default_app",
            "praisonai.ui_realtime.default_app",
        ],
    )
    def test_default_app_exports_app(self, module_path, monkeypatch):
        monkeypatch.delenv("PRAISONAI_HOST_LEGACY", raising=False)
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "app")
        assert mod.app is not None
