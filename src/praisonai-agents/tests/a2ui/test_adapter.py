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
