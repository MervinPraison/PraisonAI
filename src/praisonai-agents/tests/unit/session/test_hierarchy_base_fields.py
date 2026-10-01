"""Hierarchy deserialization retains the complete base session schema."""

from dataclasses import fields

import pytest

from praisonaiagents.session.hierarchy import ExtendedSessionData, HierarchicalSessionStore
from praisonaiagents.session.store import DefaultSessionStore, SessionData


@pytest.fixture
def base_session(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path), active_window=3)
    assert store.add_message("session", "user", "archived opening")
    for index in range(8):
        assert store.add_message("session", "user", f"later turn {index}")
    assert store.set_gateway_info("session", gateway_session_id="gateway", agent_id="agent")
    assert store.set_runtime_state("session", "native", "turn", {"status": "saved"})
    assert store.append_compaction_checkpoint("session", "resume summary", tokens_before=20, tokens_after=5)
    return store, store.get_session("session")


@pytest.mark.parametrize("operation", ["read", "set_title", "add_message"])
@pytest.mark.parametrize("field_name", ["gateway_session_id", "agent_id", "runtime_state", "last_compaction"])
def test_hierarchy_load_and_mutation_keep_base_fields(base_session, operation, field_name):
    plain, before = base_session
    # Preserve the existing archive without triggering a new compaction whose
    # legitimate anchor adjustment would obscure the deserialization contract.
    hierarchy = HierarchicalSessionStore(session_dir=plain.session_dir, active_window=100)
    if operation == "set_title":
        assert hierarchy.set_title("session", "Hierarchy title")
    elif operation == "add_message":
        assert hierarchy.add_message("session", "assistant", "new turn")
    after = hierarchy.get_extended_session("session", force_reload=True)
    assert getattr(after, field_name) == getattr(before, field_name)
    plain.invalidate_cache()
    assert getattr(plain.get_session("session"), field_name) == getattr(before, field_name)


def test_conversion_from_base_session_keeps_every_base_field(base_session):
    _, before = base_session
    after = ExtendedSessionData.from_session_data(before)
    for descriptor in fields(SessionData):
        assert getattr(after, descriptor.name) == getattr(before, descriptor.name), descriptor.name


def test_hierarchy_parser_keeps_legacy_metadata_and_precedence():
    payload = {"session_id": "legacy", "model": "recorded-model", "reasoning_effort": "high",
               "metadata": {"model": "preferred-model"}}
    base = SessionData.from_dict(payload)
    extended = ExtendedSessionData.from_dict(payload)
    assert extended.metadata == base.metadata == {"model": "preferred-model", "reasoning_effort": "high"}
    assert payload["metadata"] == {"model": "preferred-model"}


def test_extended_fields_still_round_trip():
    payload = {"session_id": "extended", "parent_id": "parent", "forked_from_message_id": "2",
               "children_ids": ["child"], "is_shared": True, "title": "Title",
               "snapshots": [{"id": "snapshot", "session_id": "extended", "message_index": 2}]}
    after = ExtendedSessionData.from_dict(payload).to_dict()
    for name in ("parent_id", "forked_from_message_id", "children_ids", "is_shared", "title"):
        assert after[name] == payload[name]
    assert after["snapshots"][0]["id"] == "snapshot"
