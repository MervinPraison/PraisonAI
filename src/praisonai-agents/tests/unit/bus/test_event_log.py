"""
Tests for the durable, queryable per-session event log (SqliteEventLog).

Covers: append+query with a per-session cursor, restart durability, best-effort
append (never raises), prune by age/count, and bus.attach_sink wiring including
the no-subscriber fast path.
"""

import time

import pytest

from praisonaiagents.bus import (
    Event,
    EventBus,
    EventType,
    SqliteEventLog,
    EventLogProtocol,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "events.sqlite")


class TestSqliteEventLog:
    def test_protocol_conformance(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        assert isinstance(log, EventLogProtocol)
        log.close()

    def test_append_and_query_ordered(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        for i in range(3):
            log.append(
                Event(
                    type=EventType.MESSAGE_CREATED.value,
                    data={"session_id": "s1", "i": i},
                )
            )
        events = log.query("s1")
        assert [e.data["i"] for e in events] == [0, 1, 2]
        assert [e.metadata["seq"] for e in events] == [1, 2, 3]
        log.close()

    def test_cursor_after_seq(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        for i in range(5):
            log.append(Event(type="custom", data={"session_id": "s1", "i": i}))
        tail = log.query("s1", after_seq=2)
        assert [e.metadata["seq"] for e in tail] == [3, 4, 5]
        log.close()

    def test_per_session_isolation(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        log.append(Event(type="custom", data={"session_id": "a"}))
        log.append(Event(type="custom", data={"session_id": "b"}))
        log.append(Event(type="custom", data={"session_id": "a"}))
        assert len(log.query("a")) == 2
        assert len(log.query("b")) == 1
        # each session has its own monotonic seq starting at 1
        assert [e.metadata["seq"] for e in log.query("a")] == [1, 2]
        assert [e.metadata["seq"] for e in log.query("b")] == [1]
        log.close()

    def test_source_used_as_session_fallback(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        log.append(Event(type=EventType.SESSION_CREATED.value, source="sess-x"))
        assert len(log.query("sess-x")) == 1
        log.close()

    def test_durable_across_restart(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        log.append(Event(type="custom", data={"session_id": "s1"}))
        log.close()

        reopened = SqliteEventLog(db_path=db_path)
        events = reopened.query("s1")
        assert len(events) == 1
        reopened.close()

    def test_append_never_raises_on_bad_data(self, db_path):
        log = SqliteEventLog(db_path=db_path)

        class Unserializable:
            pass

        # non-JSON-native payload must not raise; it is coerced via default=str
        log.append(
            Event(type="custom", data={"session_id": "s1", "obj": Unserializable()})
        )
        assert len(log.query("s1")) == 1
        log.close()

    def test_prune_by_count(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        for i in range(10):
            log.append(Event(type="custom", data={"session_id": "s1", "i": i}))
        removed = log.prune(older_than_days=0, max_rows=4)
        assert removed == 6
        remaining = log.query("s1")
        assert len(remaining) == 4
        log.close()

    def test_prune_by_age(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        old = Event(type="custom", data={"session_id": "s1"})
        old.timestamp = time.time() - 10 * 86400
        log.append(old)
        log.append(Event(type="custom", data={"session_id": "s1"}))
        removed = log.prune(older_than_days=1, max_rows=0)
        assert removed == 1
        assert len(log.query("s1")) == 1
        log.close()

    def test_seq_monotonic_after_full_prune(self, db_path):
        # Deleting every row for a session must NOT rewind the cursor, else a
        # consumer holding after_seq would silently miss the next events.
        log = SqliteEventLog(db_path=db_path)
        for _ in range(3):
            log.append(Event(type="custom", data={"session_id": "s1"}))
        assert [e.metadata["seq"] for e in log.query("s1")] == [1, 2, 3]
        # Prune everything for the session.
        log.prune(older_than_days=0, max_rows=0)
        # Force-delete all remaining rows regardless of prune heuristics.
        removed = log.prune(older_than_days=1e-9, max_rows=0)  # noqa: F841
        # Regardless of what prune left, the next seq must be > 3.
        log.append(Event(type="custom", data={"session_id": "s1"}))
        seqs = [e.metadata["seq"] for e in log.query("s1", after_seq=3)]
        assert seqs == [4], seqs
        log.close()

    def test_metadata_round_trips(self, db_path):
        log = SqliteEventLog(db_path=db_path)
        log.append(
            Event(
                type="custom",
                data={"session_id": "s1"},
                metadata={"correlation_id": "abc", "trace": 7},
            )
        )
        ev = log.query("s1")[0]
        assert ev.metadata["correlation_id"] == "abc"
        assert ev.metadata["trace"] == 7
        # durable cursor fields are still overlaid
        assert ev.metadata["seq"] == 1
        assert ev.metadata["session_id"] == "s1"
        log.close()

    def test_migrates_legacy_schema_without_collision(self, db_path):
        # A database written before event_seq/metadata_json existed must be
        # migrated so the next append continues above MAX(seq) and does not
        # collide on the primary key (silently dropping the event).
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.executescript(
            "CREATE TABLE events (session_id TEXT NOT NULL, seq INTEGER NOT NULL, "
            "ts REAL NOT NULL, type TEXT NOT NULL, event_id TEXT, source TEXT, "
            "data_json TEXT, PRIMARY KEY(session_id, seq));"
        )
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            ("s1", 1, 1.0, "custom", "id1", None, "{}"),
        )
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            ("s1", 2, 1.0, "custom", "id2", None, "{}"),
        )
        conn.commit()
        conn.close()

        log = SqliteEventLog(db_path=db_path)
        log.append(Event(type="custom", data={"session_id": "s1"}))
        seqs = [e.metadata["seq"] for e in log.query("s1")]
        assert seqs == [1, 2, 3], seqs
        log.close()

    def test_cross_connection_seq_no_collision(self, db_path):
        # Two independent instances sharing one DB file must not collide on seq.
        a = SqliteEventLog(db_path=db_path)
        b = SqliteEventLog(db_path=db_path)
        for _ in range(5):
            a.append(Event(type="custom", data={"session_id": "s1"}))
            b.append(Event(type="custom", data={"session_id": "s1"}))
        seqs = [e.metadata["seq"] for e in a.query("s1")]
        assert seqs == list(range(1, 11)), seqs
        a.close()
        b.close()


class TestBusSinkWiring:
    def test_attach_sink_persists_without_subscribers(self, db_path):
        bus = EventBus()
        log = SqliteEventLog(db_path=db_path)
        bus.attach_sink(log)
        # No subscribers: the fast path must still reach the durable sink.
        bus.publish(EventType.SESSION_CREATED, {"session_id": "s1"})
        assert len(log.query("s1")) == 1
        log.close()

    def test_detach_sink_stops_persistence(self, db_path):
        bus = EventBus()
        log = SqliteEventLog(db_path=db_path)
        bus.attach_sink(log)
        assert bus.has_sinks is True
        bus.publish("custom", {"session_id": "s1"})
        assert bus.detach_sink(log) is True
        assert bus.has_sinks is False
        bus.publish("custom", {"session_id": "s1"})
        assert len(log.query("s1")) == 1
        log.close()

    def test_no_sink_preserves_fast_path(self):
        bus = EventBus()
        # No subscribers, no sinks: publish returns an event, stores nothing.
        ev = bus.publish("custom", {"session_id": "s1"})
        assert ev.type == "custom"
        assert bus.get_history() == []

    def test_sink_failure_never_breaks_publish(self):
        bus = EventBus()

        class BadSink:
            def append(self, event):
                raise RuntimeError("boom")

        bus.attach_sink(BadSink())
        # Must not raise despite the failing sink.
        ev = bus.publish("custom", {"session_id": "s1"})
        assert ev.type == "custom"

    @pytest.mark.asyncio
    async def test_async_publish_reaches_sink(self, db_path):
        bus = EventBus()
        log = SqliteEventLog(db_path=db_path)
        bus.attach_sink(log)
        await bus.publish_async(EventType.AGENT_STARTED, {"session_id": "s1"})
        assert len(log.query("s1")) == 1
        log.close()
