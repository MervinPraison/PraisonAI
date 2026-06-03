"""Tests for A2UI artifact conversion in A2A transport."""

import json

import pytest

from praisonaiagents.ui.protocols import A2UI_MIME_TYPE


SAMPLE_A2UI_RESULT = {
    "mime_type": A2UI_MIME_TYPE,
    "messages": [{"createSurface": {"surfaceId": "main", "catalogId": "basic"}}],
    "a2ui_part": {"messages": [{"createSurface": {"surfaceId": "main", "catalogId": "basic"}}]},
}


class TestFindA2uiToolResult:
    def test_finds_last_a2ui_tool_message(self):
        from praisonaiagents.ui.a2a.conversion import find_a2ui_tool_result

        history = [
            {"role": "user", "content": "show ui"},
            {"role": "tool", "content": json.dumps({"mime_type": "text/plain", "data": "x"})},
            {"role": "tool", "content": json.dumps(SAMPLE_A2UI_RESULT)},
        ]
        result = find_a2ui_tool_result(history)
        assert result is not None
        assert result["mime_type"] == A2UI_MIME_TYPE

    def test_returns_none_without_a2ui(self):
        from praisonaiagents.ui.a2a.conversion import find_a2ui_tool_result

        assert find_a2ui_tool_result([]) is None
        assert find_a2ui_tool_result([{"role": "tool", "content": "plain text"}]) is None


class TestCreateA2uiArtifact:
    def test_creates_datapart_with_mime(self):
        from praisonaiagents.ui.a2a.conversion import create_a2ui_artifact
        from praisonaiagents.ui.a2a.types import DataPart

        artifact = create_a2ui_artifact(SAMPLE_A2UI_RESULT, name="ui-surface")
        assert artifact.name == "ui-surface"
        assert len(artifact.parts) == 1
        part = artifact.parts[0]
        assert isinstance(part, DataPart)
        assert part.metadata.get("mimeType") == A2UI_MIME_TYPE
        assert "messages" in part.data


class TestCreateResponseArtifact:
    def test_prefers_a2ui_from_history(self):
        from praisonaiagents.ui.a2a.conversion import create_response_artifact
        from praisonaiagents.ui.a2a.types import DataPart

        history = [{"role": "tool", "content": json.dumps(SAMPLE_A2UI_RESULT)}]
        artifact = create_response_artifact("Done.", chat_history=history)
        assert isinstance(artifact.parts[0], DataPart)

    def test_falls_back_to_text(self):
        from praisonaiagents.ui.a2a.conversion import create_response_artifact
        from praisonaiagents.ui.a2a.types import TextPart

        artifact = create_response_artifact("Hello", chat_history=[])
        assert isinstance(artifact.parts[0], TextPart)
        assert artifact.parts[0].text == "Hello"
