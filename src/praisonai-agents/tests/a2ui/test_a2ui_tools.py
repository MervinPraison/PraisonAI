"""Tests for send_a2ui_messages minimal arg unwrap."""

import json

import pytest

from praisonaiagents.tools.a2ui_tools import _unwrap_messages

try:
    import a2ui  # noqa: F401

    HAS_A2UI_SDK = True
except ImportError:
    HAS_A2UI_SDK = False

SAMPLE_MSG = {"createSurface": {"surfaceId": "main", "catalogId": "basic"}}


class TestUnwrapMessages:
    def test_list_input(self):
        assert _unwrap_messages([SAMPLE_MSG]) == [SAMPLE_MSG]

    def test_json_string_list(self):
        assert _unwrap_messages(json.dumps([SAMPLE_MSG])) == [SAMPLE_MSG]

    def test_wrapped_messages_dict(self):
        assert _unwrap_messages({"messages": [SAMPLE_MSG]}) == [SAMPLE_MSG]

    def test_json_string_wrapped_object(self):
        assert _unwrap_messages(json.dumps({"messages": [SAMPLE_MSG]})) == [SAMPLE_MSG]

    def test_single_message_dict(self):
        assert _unwrap_messages(SAMPLE_MSG) == [SAMPLE_MSG]

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            _unwrap_messages("{not json")

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError, match="must be"):
            _unwrap_messages(123)


@pytest.mark.skipif(not HAS_A2UI_SDK, reason="a2ui-agent-sdk not installed")
class TestSendA2uiMessagesIntegration:
    def test_full_tool_call(self):
        from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

        result = send_a2ui_messages(messages=[SAMPLE_MSG])
        assert result["mime_type"] == "application/json+a2ui"
        assert len(result["messages"]) == 1
