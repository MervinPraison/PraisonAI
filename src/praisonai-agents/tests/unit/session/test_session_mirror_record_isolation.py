"""The mirror receives a snapshot, not aliases into the caller/session cache."""

from copy import deepcopy
from threading import Event

import pytest

from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("field", ["metadata", "tool_calls"])
def test_caller_mutation_does_not_change_queued_mirror_record(tmp_path, field):
    entered, release = Event(), Event()
    received = []

    class Mirror:
        def append(self, session_id, records):
            entered.set()
            assert release.wait(10)
            received.extend(deepcopy(records))

    metadata = {"nested": {"value": "original"}}
    calls = [{"id": "call_1", "function": {"name": "lookup", "arguments": "{}"}}]
    store = DefaultSessionStore(session_dir=str(tmp_path), mirror=Mirror())
    try:
        assert store.add_message("s", "assistant", "answer", metadata=metadata, tool_calls=calls)
        assert entered.wait(10)
        if field == "metadata":
            metadata["nested"]["value"] = "mutated"
        else:
            calls[0]["function"]["name"] = "mutated"
        release.set()
        assert store.flush_mirror(timeout=10)
        durable = DefaultSessionStore(session_dir=str(tmp_path)).get_session("s")
        assert received[0][field] == durable.messages[0].to_dict()[field]
    finally:
        release.set()
        store.close_mirror()


def test_failed_sink_mutation_does_not_change_retry_payload(tmp_path):
    received = []

    class Mirror:
        attempts = 0

        def append(self, session_id, records):
            self.attempts += 1
            if self.attempts == 1:
                records[0]["metadata"]["nested"]["value"] = "failed edit"
                raise OSError("transient failure")
            received.extend(deepcopy(records))

    store = DefaultSessionStore(session_dir=str(tmp_path), mirror=Mirror())
    try:
        assert store.add_message("s", "user", "hello", metadata={
            "nested": {"value": "original"},
        })
        assert store.flush_mirror(timeout=10)
        assert received[0]["metadata"]["nested"]["value"] == "original"
    finally:
        store.close_mirror()


def test_mirror_mutation_does_not_modify_caller_or_cache(tmp_path):
    class Mirror:
        def append(self, session_id, records):
            records[0]["metadata"]["nested"]["value"] = "mirror edit"
            records[0]["tool_calls"][0]["function"]["name"] = "mirror edit"

    metadata = {"nested": {"value": "original"}}
    calls = [{"id": "call_1", "function": {"name": "lookup", "arguments": "{}"}}]
    store = DefaultSessionStore(session_dir=str(tmp_path), mirror=Mirror())
    try:
        assert store.add_message("s", "assistant", "answer", metadata=metadata, tool_calls=calls)
        assert store.flush_mirror(timeout=10)
        assert metadata["nested"]["value"] == "original"
        assert calls[0]["function"]["name"] == "lookup"
        assert store._cache["s"].messages[0].metadata == metadata
    finally:
        store.close_mirror()
