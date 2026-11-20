"""Tests for A2UI adapter (optional a2ui-agent-sdk dependency)."""

import pytest


class TestA2UIAdapterImport:
    def test_a2ui_class_export(self):
        from praisonaiagents.ui.a2ui import A2UI

        assert A2UI is not None
        assert hasattr(A2UI, "create_part")

    def test_ui_lazy_a2ui_export(self):
        from praisonaiagents.ui import A2UI

        assert A2UI is not None

    def test_missing_optional_dep_raises_clear_error(self):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        # If installed, adapter imports should work
        from praisonaiagents.ui.a2ui.adapter import create_a2ui_part

        part = create_a2ui_part({"createSurface": {"surfaceId": "main", "catalogId": "test"}})
        assert part is not None


class TestA2UITool:
    def test_send_a2ui_messages_requires_sdk(self):
        from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

        if pytest.importorskip("a2ui", reason="skip without sdk"):
            result = send_a2ui_messages(
                messages=[{"createSurface": {"surfaceId": "x", "catalogId": "c"}}]
            )
            assert result["mime_type"] == "application/json+a2ui"
            assert len(result["messages"]) == 1


class TestA2UIAdapterSmoke:
    def test_is_a2ui_part_with_sdk(self):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        from praisonaiagents.ui.a2ui.adapter import create_a2ui_part, is_a2ui_part

        part = create_a2ui_part({"messages": [{"createSurface": {"surfaceId": "m"}}]})
        assert is_a2ui_part(part) is True

    def test_create_a2ui_part_without_a2a_parts_module(self, monkeypatch):
        pytest.importorskip("a2ui", reason="a2ui-agent-sdk not installed")
        from praisonaiagents.ui.a2ui import adapter

        def _fake_import(name: str):
            if name in ("a2ui.a2a.parts", "a2ui.a2a"):
                raise ImportError("no a2a module in SDK 0.12")
            import importlib

            return importlib.import_module(name)

        monkeypatch.setattr(adapter, "_import", _fake_import)

        part = adapter.create_a2ui_part(
            {"createSurface": {"surfaceId": "main", "catalogId": "basic"}}
        )
        assert adapter.is_a2ui_part(part) is True

        from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

        result = send_a2ui_messages(
            messages=[{"createSurface": {"surfaceId": "x", "catalogId": "c"}}]
        )
        assert result["mime_type"] == "application/json+a2ui"

    def test_missing_sdk_import_error_message(self):
        from unittest.mock import patch

        from praisonaiagents.ui.a2ui import adapter

        def _raise(_name):
            raise ImportError(
                "A2UI support requires the optional dependency. "
                "Install with: pip install praisonaiagents[a2ui]"
            )

        with patch.object(adapter, "_import", side_effect=_raise):
            with pytest.raises(ImportError, match="praisonaiagents\\[a2ui\\]"):
                adapter.create_a2ui_part({"messages": []})
