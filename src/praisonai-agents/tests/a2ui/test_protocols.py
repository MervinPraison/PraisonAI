"""Tests for UI protocol types (zero-dep contracts)."""

from praisonaiagents.ui.protocols import A2UI_MIME_TYPE, A2UIToolResultProtocol


class TestA2UIProtocols:
    def test_mime_type_constant(self):
        assert A2UI_MIME_TYPE == "application/json+a2ui"

    def test_tool_result_protocol_shape(self):
        result: A2UIToolResultProtocol = {
            "mime_type": A2UI_MIME_TYPE,
            "messages": [{"createSurface": {"surfaceId": "main"}}],
            "a2ui_part": {"messages": []},
        }
        assert result["mime_type"] == A2UI_MIME_TYPE

    def test_exported_from_a2ui_package(self):
        from praisonaiagents.ui.a2ui import A2UI_MIME_TYPE, A2UIToolResultProtocol

        assert A2UI_MIME_TYPE == "application/json+a2ui"
        assert A2UIToolResultProtocol is not None

    def test_top_level_lazy_a2ui_export(self):
        from praisonaiagents import A2UI

        assert A2UI is not None
