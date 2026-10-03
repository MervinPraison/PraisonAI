"""The mirror receives a snapshot, not aliases into the caller/session cache."""

from copy import deepcopy
from threading import Event
import threading

import pytest

from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("field", ["metadata", "tool_calls"])
def test_json_container_subclass_does_not_fail_local_add(tmp_path, field):
    class Mapping(dict):
        pass

    class Sequence(list):
        pass

    received = []

    class Mirror:
        def append(self, session_id, records):
            received.extend(deepcopy(records))

    metadata = Mapping({"value": "original"})
    calls = Sequence([{"id": "call_1", "function": {"name": "lookup", "arguments": "{}"}}])
    container = metadata if field == "metadata" else calls
    container.lock = threading.Lock()
    store = DefaultSessionStore(session_dir=str(tmp_path), mirror=Mirror())
    try:
        assert store.add_message("s", "assistant", "hello", metadata=metadata, tool_calls=calls)
        assert store.flush_mirror(timeout=10)
        durable = DefaultSessionStore(session_dir=str(tmp_path)).get_session("s")
        assert received[0][field] == durable.messages[0].to_dict()[field]
    finally:
        store.close_mirror()


def test_mirror_preparation_failure_keeps_local_success(tmp_path, monkeypatch, caplog):
    import praisonaiagents.session.store as store_module

    class Mirror:
        def append(self, session_id, records):
            raise AssertionError("failed preparation must not enqueue a record")

    store = DefaultSessionStore(session_dir=str(tmp_path), mirror=Mirror())

    def fail(*args, **kwargs):
        raise TypeError("snapshot preparation failed")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(store_module.json, "dumps", fail)
            assert store.add_message("s", "user", "durable")
        assert store.flush_mirror(timeout=10)
        assert DefaultSessionStore(session_dir=str(tmp_path)).get_chat_history("s") == [
            {"role": "user", "content": "durable"},
        ]
        assert "local write unaffected" in caplog.text
    finally:
        store.close_mirror()


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
