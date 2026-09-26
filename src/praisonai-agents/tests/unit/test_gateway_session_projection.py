"""Regression coverage for the session-projection reducer (Issue #5324).

The reducer is the missing SDK primitive that turns a raw gateway event stream
into a correct, resumable view. These tests pin the behaviours that every
client would otherwise re-implement: snapshot+event folding, identity
de-duplication of a final message that arrives both as a stream and as a
persisted row, optimistic echo reconciliation, transport-gap detection, and
bounded run retention.
"""

from praisonaiagents.gateway import (
    EventType,
    GatewayEvent,
    GatewayMessage,
    RunView,
    SessionProjection,
    SessionProjectionState,
)
from praisonaiagents.gateway.session_projection import (
    SessionProjection as ModuleProjection,
)


def _msg(message_id, content="hi", request_id=None, sender="agent"):
    metadata = {"request_id": request_id} if request_id else {}
    return GatewayMessage(
        content=content,
        sender_id=sender,
        session_id="s1",
        message_id=message_id,
        metadata=metadata,
    )


def _message_event(message, request_id=None):
    data = {"message": message.to_dict()}
    if request_id:
        data["request_id"] = request_id
    return GatewayEvent(type=EventType.MESSAGE, data=data)


def test_lazy_exports_resolve_to_module():
    """Gateway lazy exports resolve to the concrete reducer classes."""
    assert SessionProjection is ModuleProjection


def test_empty_state_defaults():
    proj = SessionProjection()
    state = proj.state
    assert isinstance(state, SessionProjectionState)
    assert state.entries == ()
    assert state.runs == {}
    assert state.has_transport_gap is False


def test_apply_snapshot_seeds_entries():
    proj = SessionProjection()
    state = proj.apply_snapshot(
        {"messages": [_msg("m1").to_dict(), _msg("m2").to_dict()], "cursor": 5}
    )
    ids = [m.message_id for m in state.entries]
    assert ids == ["m1", "m2"]


def test_message_event_appends_once():
    proj = SessionProjection()
    proj.apply(_message_event(_msg("m1")))
    state = proj.apply(_message_event(_msg("m2")))
    assert [m.message_id for m in state.entries] == ["m1", "m2"]


def test_identity_dedup_final_message_renders_once():
    """A final message seen twice (stream_end + persisted row) renders once."""
    proj = SessionProjection()
    # Stream the final answer.
    proj.apply(
        GatewayEvent(type="delta_text", data={"run_id": "r1", "delta": "Hello"})
    )
    proj.apply(
        GatewayEvent(
            type=EventType.STREAM_END,
            data={"run_id": "r1", "message_id": "final-1"},
        )
    )
    # The same answer arrives as a durable transcript row, twice.
    final = _msg("final-1", content="Hello")
    proj.apply(_message_event(final))
    state = proj.apply(_message_event(final))
    assert [m.message_id for m in state.entries] == ["final-1"]
    assert state.runs["r1"].done is True
    assert state.runs["r1"].final_message_id == "final-1"


def test_optimistic_echo_reconciled_by_request_id():
    """A local echo is replaced (not duplicated) by its durable counterpart."""
    proj = SessionProjection()
    echo = _msg("local-echo", content="draft", request_id="req-42", sender="user")
    proj.apply(_message_event(echo, request_id="req-42"))
    durable = _msg("server-id", content="draft", request_id="req-42", sender="user")
    state = proj.apply(_message_event(durable, request_id="req-42"))
    assert len(state.entries) == 1
    assert state.entries[0].message_id == "server-id"


def test_transport_gap_flag_on_sequence_hole():
    proj = SessionProjection()
    proj.apply(GatewayEvent(type=EventType.MESSAGE, data={}, sequence=1))
    assert proj.state.has_transport_gap is False
    proj.apply(GatewayEvent(type=EventType.MESSAGE, data={}, sequence=5))
    assert proj.state.has_transport_gap is True


def test_snapshot_clears_gap_and_converges():
    proj = SessionProjection()
    proj.apply(GatewayEvent(type=EventType.MESSAGE, data={}, sequence=1))
    proj.apply(GatewayEvent(type=EventType.MESSAGE, data={}, sequence=9))
    assert proj.state.has_transport_gap is True
    # A resync delivers a fresh snapshot; the view converges without dupes.
    state = proj.apply_snapshot({"messages": [_msg("m1").to_dict()], "cursor": 9})
    assert state.has_transport_gap is False
    assert [m.message_id for m in state.entries] == ["m1"]


def test_delta_accumulates_per_run():
    proj = SessionProjection()
    proj.apply(GatewayEvent(type="delta_text", data={"run_id": "r1", "delta": "Hel"}))
    proj.apply(GatewayEvent(type="delta_text", data={"run_id": "r1", "delta": "lo"}))
    run = proj.state.runs["r1"]
    assert isinstance(run, RunView)
    assert run.text == "Hello"
    assert run.done is False


def test_bounded_retention_evicts_finished_runs():
    proj = SessionProjection(max_tracked_runs=2)
    for i in range(5):
        rid = f"r{i}"
        proj.apply(GatewayEvent(type="delta_text", data={"run_id": rid, "delta": "x"}))
        proj.apply(GatewayEvent(type=EventType.STREAM_END, data={"run_id": rid}))
    assert len(proj.state.runs) <= 2


def test_active_stream_never_evicted():
    proj = SessionProjection(max_tracked_runs=1)
    # Active (unfinished) run.
    proj.apply(GatewayEvent(type="delta_text", data={"run_id": "active", "delta": "x"}))
    # Many finished runs pushing past the cap.
    for i in range(4):
        rid = f"done{i}"
        proj.apply(GatewayEvent(type="delta_text", data={"run_id": rid, "delta": "y"}))
        proj.apply(GatewayEvent(type=EventType.STREAM_END, data={"run_id": rid}))
    assert "active" in proj.state.runs
    assert proj.state.runs["active"].done is False


def test_apply_returns_immutable_state():
    proj = SessionProjection()
    s1 = proj.apply(_message_event(_msg("m1")))
    entries_before = s1.entries
    proj.apply(_message_event(_msg("m2")))
    # The previously-returned snapshot is not mutated in place.
    assert entries_before == s1.entries
    assert len(entries_before) == 1


def test_invalid_max_tracked_runs_rejected():
    import pytest

    with pytest.raises(ValueError):
        SessionProjection(max_tracked_runs=0)
