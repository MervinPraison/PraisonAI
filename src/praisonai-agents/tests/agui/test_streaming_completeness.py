"""Every StreamEventType must have a declared AG-UI disposition.

The adapter's fall-through `return []` means an unmapped event type is dropped
with no error and no log. That is invisible for cosmetic events and data loss
for ERROR, RETRY, MODEL_FALLBACK and STREAM_UNAVAILABLE: the client sees a run
that ends cleanly having never been told anything went wrong.

This suite pins the disposition of all sixteen members. Adding a new
StreamEventType without deciding whether it crosses the wire fails the first
test, by construction.
"""

import pytest

from praisonaiagents.streaming.events import StreamEvent, StreamEventType
from praisonaiagents.ui.agui.streaming import (
    EventBuffer,
    NOT_WIRE_VISIBLE,
    stream_event_to_agui_events,
)


def _event(event_type: StreamEventType) -> StreamEvent:
    """A populated event, so a drop is never merely an empty payload."""
    return StreamEvent(
        type=event_type,
        content="text",
        tool_call={"id": "call-1", "name": "f", "arguments": {}, "result": "r"},
        error="boom",
    )


def test_every_event_type_has_a_declared_disposition():
    undeclared = [
        t.name
        for t in StreamEventType
        if not stream_event_to_agui_events(_event(t), "m1", EventBuffer())
        and t not in NOT_WIRE_VISIBLE
    ]
    assert not undeclared, (
        "these StreamEventTypes are silently dropped by the AG-UI adapter and are "
        f"not declared in NOT_WIRE_VISIBLE: {undeclared}"
    )


@pytest.mark.parametrize(
    "event_type",
    [
        StreamEventType.ERROR,
        StreamEventType.STREAM_UNAVAILABLE,
        StreamEventType.RETRY,
        StreamEventType.MODEL_FALLBACK,
    ],
)
def test_failure_events_reach_the_client(event_type):
    """A failure the engine recovered from is still news the client must get."""
    out = stream_event_to_agui_events(_event(event_type), "m1", EventBuffer())
    assert out, f"{event_type.name} produced no AG-UI event: the client is never told"


def test_not_wire_visible_is_a_closed_set_of_real_members():
    """Guards against silencing a type by adding a typo to the allowlist."""
    for member in NOT_WIRE_VISIBLE:
        assert isinstance(member, StreamEventType)


def test_mapped_events_still_map():
    """Positive control: the three handled types must keep working."""
    for event_type in (
        StreamEventType.DELTA_TEXT,
        StreamEventType.TOOL_CALL_START,
        StreamEventType.TOOL_CALL_RESULT,
    ):
        assert stream_event_to_agui_events(_event(event_type), "m1", EventBuffer())


def test_tool_call_delta_id_survives_id_less_chunks():
    """Providers send the id once; later argument chunks must keep that id.

    A fresh UUID per chunk would orphan the arguments from the invocation the
    AG-UI client is assembling.
    """
    buffer = EventBuffer()

    start = StreamEvent(
        type=StreamEventType.TOOL_CALL_START,
        tool_call={"id": "call-42", "name": "f", "arguments": {}},
    )
    (start_out := stream_event_to_agui_events(start, "m1", buffer))
    assert any(getattr(e, "tool_call_id", None) == "call-42" for e in start_out)

    chunk = StreamEvent(
        type=StreamEventType.DELTA_TOOL_CALL,
        tool_call={"arguments": '{"x":'},
    )
    chunk_out = stream_event_to_agui_events(chunk, "m1", buffer)
    assert [e.tool_call_id for e in chunk_out] == ["call-42"]

    end = StreamEvent(type=StreamEventType.TOOL_CALL_END, tool_call={})
    end_out = stream_event_to_agui_events(end, "m1", buffer)
    assert [e.tool_call_id for e in end_out] == ["call-42"]
