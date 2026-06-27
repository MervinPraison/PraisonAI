"""Tests for multimodal tool output (images/files) becoming model-visible.

Validates the core tool-result contract added in tools/base.py and the
tool-result -> message formatting in agent/tool_execution.py.
"""

import base64

import pytest

from praisonaiagents.tools import (
    ToolResult,
    multimodal_content,
    text_part,
    image_part,
    file_part,
)
from praisonaiagents.agent.tool_execution import (
    format_tool_result_messages,
    _normalize_multimodal_result,
)


FAKE_PNG = b"\x89PNG\r\n\x1a\n fake-image-bytes"


class TestToolResultContract:
    def test_plain_toolresult_not_multimodal(self):
        r = ToolResult(output="hello")
        assert r.is_multimodal is False
        assert str(r) == "hello"
        assert "content" not in r.to_dict()

    def test_multimodal_toolresult_flags(self):
        r = multimodal_content(
            text_part("here is the screen"),
            image_part(FAKE_PNG, mime="image/png", name="s.png"),
        )
        assert r.is_multimodal is True
        assert "content" in r.to_dict()
        # __str__ falls back to text parts when output is None
        assert "here is the screen" in str(r)

    def test_image_part_helpers(self):
        p = image_part(FAKE_PNG, mime="image/jpeg", name="x.jpg")
        assert p == {
            "type": "image",
            "mime": "image/jpeg",
            "data": FAKE_PNG,
            "name": "x.jpg",
        }
        u = image_part(url="https://example.com/a.png")
        assert u == {"type": "image", "mime": "image/png", "url": "https://example.com/a.png"}

    def test_file_part_helper(self):
        p = file_part(b"abc", mime="application/pdf", name="doc.pdf")
        assert p["type"] == "file"
        assert p["mime"] == "application/pdf"
        assert p["name"] == "doc.pdf"


class TestFormatToolResultMessages:
    def test_plain_text_returns_none(self):
        assert format_tool_result_messages("just text", "call_1") is None

    def test_plain_dict_returns_none(self):
        assert format_tool_result_messages({"foo": "bar"}, "call_1") is None

    def test_plain_toolresult_returns_none(self):
        assert format_tool_result_messages(ToolResult(output="x"), "call_1") is None

    def test_multimodal_toolresult_emits_two_messages(self):
        r = multimodal_content(
            text_part("here is the screen"),
            image_part(FAKE_PNG, mime="image/png", name="s.png"),
        )
        msgs = format_tool_result_messages(r, "call_1")
        assert msgs is not None
        assert len(msgs) == 2
        # First message satisfies the tool_call_id contract
        assert msgs[0]["role"] == "tool"
        assert msgs[0]["tool_call_id"] == "call_1"
        assert "here is the screen" in msgs[0]["content"]
        # Second message carries model-visible parts
        assert msgs[1]["role"] == "user"
        types = [p["type"] for p in msgs[1]["content"]]
        assert "image_url" in types
        img = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert img["image_url"]["url"].startswith("data:image/png;base64,")
        decoded = base64.b64decode(img["image_url"]["url"].split(",", 1)[1])
        assert decoded == FAKE_PNG

    def test_image_via_url(self):
        r = ToolResult(output=None, content=[image_part(url="https://x/y.png")])
        msgs = format_tool_result_messages(r, "call_2")
        assert msgs is not None
        img = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert img["image_url"]["url"] == "https://x/y.png"

    def test_base64_string_data(self):
        encoded = base64.b64encode(FAKE_PNG).decode()
        r = ToolResult(output=None, content=[image_part(encoded, mime="image/png")])
        msgs = format_tool_result_messages(r, "call_3")
        img = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert img["image_url"]["url"] == f"data:image/png;base64,{encoded}"

    def test_data_uri_passthrough(self):
        uri = "data:image/png;base64,QUJD"
        r = ToolResult(output=None, content=[image_part(uri, mime="image/png")])
        msgs = format_tool_result_messages(r, "call_4")
        img = next(p for p in msgs[1]["content"] if p["type"] == "image_url")
        assert img["image_url"]["url"] == uri

    def test_mcp_style_list(self):
        mcp = [
            {"type": "text", "text": "desc"},
            {"type": "image", "data": base64.b64encode(FAKE_PNG).decode(), "mimeType": "image/png"},
        ]
        msgs = format_tool_result_messages(mcp, "call_5")
        assert msgs is not None
        types = [p["type"] for p in msgs[1]["content"]]
        assert "image_url" in types

    def test_text_only_content_returns_none(self):
        # No media -> let the normal text path handle it
        r = ToolResult(output=None, content=[text_part("just words")])
        assert format_tool_result_messages(r, "call_6") is None

    def test_oversized_image_skipped(self):
        big = b"x" * (5_000_001)
        r = ToolResult(output=None, content=[image_part(big, mime="image/png")])
        # oversized image is dropped -> no media -> returns None
        assert format_tool_result_messages(r, "call_7") is None

    def test_text_fallback_used_for_tool_message(self):
        r = multimodal_content(image_part(FAKE_PNG, mime="image/png"))
        msgs = format_tool_result_messages(r, "call_8", text_fallback="custom summary")
        assert msgs[0]["content"] == "custom summary"


class TestNormalizeMultimodalResult:
    def test_none_for_scalars(self):
        assert _normalize_multimodal_result("text") is None
        assert _normalize_multimodal_result(123) is None
        assert _normalize_multimodal_result({"a": 1}) is None

    def test_detects_toolresult_content(self):
        r = multimodal_content(image_part(FAKE_PNG))
        parts = _normalize_multimodal_result(r)
        assert parts and parts[0]["type"] == "image"

    def test_detects_single_image_dict(self):
        d = {"type": "image", "data": FAKE_PNG, "mime": "image/png"}
        parts = _normalize_multimodal_result(d)
        assert parts and parts[0]["type"] == "image"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
