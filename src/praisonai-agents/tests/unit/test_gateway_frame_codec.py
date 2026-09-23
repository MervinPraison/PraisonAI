"""Unit tests for the schema-validated inbound frame codec (Issue #2831).

Covers the core-side ``decode_client_frame`` dispatcher and the typed frame
classes (``HelloParams``/``MessageParams``/``LeaveParams``/``JoinParams``),
verifying that valid frames decode into typed objects and that malformed /
hostile frames are rejected deterministically with a structured ``HelloError``.
"""

import pytest

from praisonaiagents.gateway import (
    ConnectErrorCode,
    FrameDecodeError,
    HelloError,
    HelloParams,
    JoinParams,
    LeaveParams,
    MessageParams,
    decode_client_frame,
)


# --------------------------------------------------------------------------- #
# hello
# --------------------------------------------------------------------------- #
def test_hello_direct_fields():
    frame = decode_client_frame({
        "type": "hello",
        "agent_id": "agent-1",
        "protocol_min": 1,
        "protocol_max": 2,
        "capabilities": ["streaming", "ack"],
        "session_id": "sess-1",
        "since": 10,
    })
    assert isinstance(frame, HelloParams)
    assert frame.type == "hello"
    assert frame.agent_id == "agent-1"
    assert frame.protocol_min == 1
    assert frame.protocol_max == 2
    assert frame.capabilities == ["streaming", "ack"]
    assert frame.session_id == "sess-1"
    assert frame.since == 10


def test_hello_legacy_nested_protocol_and_caps_alias():
    frame = decode_client_frame({
        "type": "hello",
        "agent_id": "agent-1",
        "protocol": {"min": 1, "max": 3},
        "caps": ["presence"],
    })
    assert isinstance(frame, HelloParams)
    assert frame.protocol_min == 1
    assert frame.protocol_max == 3
    assert frame.capabilities == ["presence"]


def test_hello_missing_protocol_defaults_to_v1():
    frame = decode_client_frame({"type": "hello", "agent_id": "agent-1"})
    assert frame.protocol_min == 1
    assert frame.protocol_max == 1
    assert frame.capabilities == []


def test_hello_missing_agent_id_rejected():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({"type": "hello"})
    assert isinstance(exc.value.error, HelloError)
    assert exc.value.error.code == ConnectErrorCode.CONFIGURATION_ERROR


def test_hello_non_integer_protocol_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "hello", "agent_id": "a", "protocol_min": "abc",
        })


def test_hello_boolean_protocol_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "hello", "agent_id": "a", "protocol_min": True,
        })


def test_hello_integral_string_protocol_coerced():
    frame = decode_client_frame({
        "type": "hello", "agent_id": "a", "protocol_min": "1", "protocol_max": "2",
    })
    assert frame.protocol_min == 1
    assert frame.protocol_max == 2


def test_hello_inverted_version_range_rejected():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({
            "type": "hello", "agent_id": "a",
            "protocol_min": 5, "protocol_max": 1,
        })
    assert exc.value.error.code == ConnectErrorCode.PROTOCOL_UNSUPPORTED


def test_hello_null_capabilities_becomes_empty_list():
    frame = decode_client_frame({
        "type": "hello", "agent_id": "a", "capabilities": None,
    })
    assert frame.capabilities == []


# --------------------------------------------------------------------------- #
# message
# --------------------------------------------------------------------------- #
def test_message_valid():
    frame = decode_client_frame({
        "type": "message",
        "content": "hello world",
        "session_id": "s1",
        "message_id": "m1",
        "metadata": {"k": "v"},
    })
    assert isinstance(frame, MessageParams)
    assert frame.content == "hello world"
    assert frame.session_id == "s1"
    assert frame.message_id == "m1"
    assert frame.metadata == {"k": "v"}
    assert frame.type == "message"


def test_message_text_alias():
    frame = decode_client_frame({"type": "message", "text": "hi"})
    assert frame.content == "hi"


def test_message_object_content():
    frame = decode_client_frame({"type": "message", "content": {"parts": [1]}})
    assert frame.content == {"parts": [1]}


def test_message_missing_content_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({"type": "message"})


def test_message_empty_content_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({"type": "message", "content": ""})


def test_message_invalid_content_type_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({"type": "message", "content": 123})


# --------------------------------------------------------------------------- #
# message attachments (Issue #5207)
# --------------------------------------------------------------------------- #
def test_message_without_attachments_defaults_empty():
    """A message frame with no attachments decodes exactly as before."""
    frame = decode_client_frame({"type": "message", "content": "hi"})
    assert frame.attachments == []


def test_message_inline_attachment():
    frame = decode_client_frame({
        "type": "message",
        "content": "analyse this",
        "attachments": [
            {"filename": "a.png", "mime": "image/png", "size": 3, "data": "AAA="},
        ],
    })
    assert len(frame.attachments) == 1
    att = frame.attachments[0]
    assert att.filename == "a.png"
    assert att.mime == "image/png"
    assert att.size == 3
    assert att.data == "AAA="
    assert att.ref_id is None
    assert att.to_dict() == {
        "filename": "a.png", "mime": "image/png", "size": 3, "data": "AAA=",
    }


def test_message_ref_attachment():
    frame = decode_client_frame({
        "type": "message",
        "content": "summarise",
        "attachments": [
            {"filename": "b.pdf", "mime": "application/pdf", "size": 100, "ref_id": "r1"},
        ],
    })
    att = frame.attachments[0]
    assert att.ref_id == "r1"
    assert att.data is None
    assert att.to_dict() == {
        "filename": "b.pdf", "mime": "application/pdf", "size": 100, "ref_id": "r1",
    }


def test_message_attachment_without_carrier_rejected():
    """An attachment carrying neither inline data nor a store ref_id is rejected."""
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "message",
            "content": "x",
            "attachments": [{"filename": "c", "mime": "text/plain", "size": 1}],
        })


def test_message_attachment_missing_filename_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "message",
            "content": "x",
            "attachments": [{"mime": "text/plain", "size": 1, "data": "AA=="}],
        })


def test_message_attachments_not_a_list_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "message", "content": "x", "attachments": "notalist",
        })


def test_message_attachment_negative_size_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "message",
            "content": "x",
            "attachments": [
                {"filename": "c", "mime": "text/plain", "size": -1, "data": "AA=="},
            ],
        })


# --------------------------------------------------------------------------- #
# leave
# --------------------------------------------------------------------------- #
def test_leave_valid():
    frame = decode_client_frame({
        "type": "leave", "session_id": "s1", "reason": "done",
    })
    assert isinstance(frame, LeaveParams)
    assert frame.session_id == "s1"
    assert frame.reason == "done"
    assert frame.type == "leave"


def test_leave_minimal():
    frame = decode_client_frame({"type": "leave"})
    assert isinstance(frame, LeaveParams)
    assert frame.session_id is None
    assert frame.reason is None


# --------------------------------------------------------------------------- #
# join (legacy)
# --------------------------------------------------------------------------- #
def test_join_valid():
    frame = decode_client_frame({
        "type": "join",
        "agent_id": "agent-1",
        "min_version": 1,
        "max_version": 2,
        "session_id": "s1",
    })
    assert isinstance(frame, JoinParams)
    assert frame.agent_id == "agent-1"
    assert frame.min_version == 1
    assert frame.max_version == 2
    assert frame.session_id == "s1"


def test_join_defaults_version_range():
    frame = decode_client_frame({"type": "join", "agent_id": "a"})
    assert frame.min_version == 1
    assert frame.max_version >= frame.min_version


def test_join_invalid_version_fields_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({
            "type": "join", "agent_id": "a", "min_version": "x",
        })


def test_join_inverted_range_rejected():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({
            "type": "join", "agent_id": "a", "min_version": 9, "max_version": 1,
        })
    assert exc.value.error.code == ConnectErrorCode.PROTOCOL_UNSUPPORTED


def test_join_missing_agent_id_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame({"type": "join"})


# --------------------------------------------------------------------------- #
# dispatcher / hostile frames
# --------------------------------------------------------------------------- #
def test_non_dict_frame_rejected():
    with pytest.raises(FrameDecodeError):
        decode_client_frame("not a frame")  # type: ignore[arg-type]


def test_missing_type_rejected():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({"agent_id": "a"})
    assert exc.value.error.code == ConnectErrorCode.CONFIGURATION_ERROR


def test_unknown_type_rejected():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({"type": "definitely_not_a_method"})
    assert exc.value.error.code == ConnectErrorCode.CONFIGURATION_ERROR


def test_decode_error_carries_serialisable_hello_error():
    with pytest.raises(FrameDecodeError) as exc:
        decode_client_frame({"type": "hello"})
    payload = exc.value.error.to_dict()
    assert isinstance(payload, dict)
    assert "code" in payload


def test_every_frame_type_exposes_type_discriminant():
    frames = [
        decode_client_frame({"type": "hello", "agent_id": "a"}),
        decode_client_frame({"type": "message", "content": "hi"}),
        decode_client_frame({"type": "leave"}),
        decode_client_frame({"type": "join", "agent_id": "a"}),
    ]
    assert [f.type for f in frames] == ["hello", "message", "leave", "join"]
