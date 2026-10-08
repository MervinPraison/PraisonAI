"""Malformed indexed transcript messages must not interrupt gateway routing.

Issue #5672 (follow-up to #5628): replacing an indexed transcript message with
JSON ``null``, a string, or a number made ``get_by_gateway_session`` raise
``AttributeError`` from ``SessionMessage.from_dict``'s ``.get`` calls -- both
active and archived messages were affected, across the SQLite indexed route and
the default-store scan fallback.

An unreadable turn must now be skipped: the route resolves (or returns ``None``)
without crashing, healthy sessions stay routable, and the original on-disk
transcript and its index record are left untouched.
"""

import json
import os
import tempfile

import pytest

from praisonaiagents.session.store import (
    CompactionCheckpoint,
    DefaultSessionStore,
    SessionData,
)
from praisonaiagents.session import SqliteSessionStore, SqliteTranscriptStore


@pytest.fixture
def tmp_dir(monkeypatch):
    """Temp dir that closes any SQLite store connection before cleanup.

    On Windows an open SQLite connection keeps ``sessions.db`` /
    ``sessions_index.db`` locked, so ``TemporaryDirectory`` teardown raises
    ``WinError 32`` ("file in use"). Track every ``SqliteSessionStore`` /
    ``SqliteTranscriptStore`` created during the test and close its live
    ``_conn`` in a ``finally`` block before the directory is removed. This is a
    test-only safeguard -- production source is untouched.
    """
    created = []
    for cls in (SqliteSessionStore, SqliteTranscriptStore):
        original_init = cls.__init__

        def _tracking_init(self, *args, _orig=original_init, **kwargs):
            _orig(self, *args, **kwargs)
            created.append(self)

        monkeypatch.setattr(cls, "__init__", _tracking_init)

    try:
        with tempfile.TemporaryDirectory() as d:
            try:
                yield d
            finally:
                for store in created:
                    conn = getattr(store, "_conn", None)
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        store._conn = None
    finally:
        created.clear()


MALFORMED = {"null": None, "string": "oops", "number": 42}


@pytest.mark.parametrize("label", list(MALFORMED))
@pytest.mark.parametrize("field", ["messages", "archived_messages"])
def test_from_dict_skips_non_dict_turns(label, field):
    """The root cause: ``SessionData.from_dict`` tolerates non-object turns."""
    bad = MALFORMED[label]
    data = {
        "session_id": "s1",
        "messages": [{"role": "user", "content": "hi"}],
        "archived_messages": [{"role": "assistant", "content": "older"}],
        "gateway_session_id": "gw-1",
    }
    data[field] = [bad] + data[field]

    session = SessionData.from_dict(data)

    assert session.gateway_session_id == "gw-1"
    # The malformed entry is dropped; the healthy turn survives.
    kept = session.messages if field == "messages" else session.archived_messages
    assert [m.content for m in kept] == (
        ["hi"] if field == "messages" else ["older"]
    )


@pytest.mark.parametrize("label", list(MALFORMED))
def test_from_dict_shifts_compaction_anchor_for_dropped_active_turns(label):
    """Dropping an active turn before the anchor must shift ``message_index``.

    Greptile P1 (Issue #2741 interaction): ``[bad, old_turn, new_turn]`` with
    ``message_index=2`` must not become ``[old_turn, new_turn]`` with the anchor
    still at 2 -- that slices the tail from the end and ``get_working_history``
    returns only the summary, silently dropping both healthy post-compaction
    turns. The anchor is decremented by the one entry dropped before it, so the
    retained tail (``new_turn``) survives.
    """
    data = {
        "session_id": "s1",
        "messages": [
            MALFORMED[label],
            {"role": "assistant", "content": "old_turn"},
            {"role": "user", "content": "new_turn"},
        ],
        "last_compaction": CompactionCheckpoint(
            summary="SUMMARY", message_index=2
        ).to_dict(),
    }

    session = SessionData.from_dict(data)

    # One malformed entry dropped before the anchor -> anchor shifts 2 -> 1.
    assert session.last_compaction.message_index == 1
    assert [m.content for m in session.messages] == ["old_turn", "new_turn"]

    history = session.get_working_history()
    # Summary head + the retained tail turn that would otherwise be lost.
    assert history[0]["content"] == "SUMMARY"
    assert any(m.get("content") == "new_turn" for m in history)


def test_from_dict_leaves_anchor_when_drop_is_after_boundary():
    """A malformed turn *after* the anchor leaves ``message_index`` unchanged."""
    data = {
        "session_id": "s1",
        "messages": [
            {"role": "assistant", "content": "old_turn"},
            None,
            {"role": "user", "content": "new_turn"},
        ],
        "last_compaction": CompactionCheckpoint(
            summary="SUMMARY", message_index=1
        ).to_dict(),
    }

    session = SessionData.from_dict(data)

    assert session.last_compaction.message_index == 1
    assert [m.content for m in session.messages] == ["old_turn", "new_turn"]
    history = session.get_working_history()
    assert history[0]["content"] == "SUMMARY"
    assert any(m.get("content") == "new_turn" for m in history)


@pytest.mark.parametrize("label", list(MALFORMED))
@pytest.mark.parametrize("field", ["messages", "archived_messages"])
def test_sqlite_indexed_route_survives_malformed_turn(tmp_dir, label, field):
    """Indexed route resolves despite a malformed active/archived turn."""
    db = os.path.join(tmp_dir, "sessions.db")
    store = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
    store.add_message("s1", "user", "hi")
    store.set_gateway_info("s1", gateway_session_id="gw-1", agent_id="agent-x")

    # Corrupt a single stored turn in place, preserving the index record.
    with store._db_lock:  # noqa: SLF001 - test reaches into the durable row
        conn = store._connect()
        row = conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?", ("s1",)
        ).fetchone()
        data = json.loads(row[0])
        data.setdefault("archived_messages", [{"role": "assistant", "content": "a"}])
        data[field] = [MALFORMED[label]] + data.get(field, [])
        conn.execute(
            "UPDATE sessions SET data = ? WHERE session_id = ?",
            (json.dumps(data, ensure_ascii=False), "s1"),
        )
        conn.commit()

    found = store.get_by_gateway_session("gw-1")
    assert found is not None
    assert found.session_id == "s1"

    # Index record and raw transcript are preserved (not quarantined/deleted).
    assert store.list_sessions_by_gateway_agent("agent-x") == ["s1"]
    with store._db_lock:  # noqa: SLF001
        conn = store._connect()
        raw = conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?", ("s1",)
        ).fetchone()
    assert MALFORMED[label] in json.loads(raw[0])[field]


@pytest.mark.parametrize("label", list(MALFORMED))
@pytest.mark.parametrize("field", ["messages", "archived_messages"])
def test_sqlite_indexed_route_on_disk_survives_malformed_turn(tmp_dir, label, field):
    """The originally reported crash path: ``SqliteSessionStore._read_indexed_route``.

    Unlike ``SqliteTranscriptStore`` (which stores turns in the ``sessions``
    table), ``SqliteSessionStore`` keeps the transcript as an on-disk JSON file
    and routes via the ``session_route`` index. Issue #5672's ``AttributeError``
    surfaced here, so corrupt the durable JSON directly and confirm the indexed
    lookup still resolves without touching the file or its route record.
    """
    store = SqliteSessionStore(
        session_dir=tmp_dir, db_path=os.path.join(tmp_dir, "sessions_index.db")
    )
    store.add_message("s1", "user", "hi")
    store.set_gateway_info("s1", gateway_session_id="gw-1", agent_id="agent-x")

    filepath = store._get_session_path("s1")  # noqa: SLF001
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("archived_messages", [{"role": "assistant", "content": "a"}])
    data[field] = [MALFORMED[label]] + data.get(field, [])
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    found = store.get_by_gateway_session("gw-1")
    assert found is not None
    assert found.session_id == "s1"

    # Index record and raw on-disk transcript are preserved, not quarantined.
    assert store.list_sessions_by_gateway_agent("agent-x") == ["s1"]
    with open(filepath, "r", encoding="utf-8") as f:
        assert MALFORMED[label] in json.load(f)[field]


@pytest.mark.parametrize("label", list(MALFORMED))
@pytest.mark.parametrize("field", ["messages", "archived_messages"])
def test_default_store_scan_survives_malformed_turn(tmp_dir, label, field):
    """Default-store scan fallback resolves despite a malformed turn."""
    store = DefaultSessionStore(session_dir=tmp_dir)
    store.add_message("s1", "user", "hi")
    store.set_gateway_info("s1", gateway_session_id="gw-1", agent_id="agent-x")

    filepath = store._get_session_path("s1")  # noqa: SLF001
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("archived_messages", [{"role": "assistant", "content": "a"}])
    data[field] = [MALFORMED[label]] + data.get(field, [])
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    found = store.get_by_gateway_session("gw-1")
    assert found is not None
    assert found.session_id == "s1"

    # Original transcript left untouched on disk.
    with open(filepath, "r", encoding="utf-8") as f:
        assert MALFORMED[label] in json.load(f)[field]
