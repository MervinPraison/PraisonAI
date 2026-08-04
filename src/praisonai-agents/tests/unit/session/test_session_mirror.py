"""Tests for the local-first session mirror (Issue #3646).

Covers the core, unblocked half of the sessions-sync work: the
``SessionMirrorProtocol`` contract and the optional, non-blocking dual-write
hook on ``DefaultSessionStore``. The heavy backend adapters + ``session sync``
CLI live in the wrapper and depend on the store-unification sibling (#3645).
"""

import tempfile
import threading
import time

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.protocols import SessionMirrorProtocol


class _RecordingMirror:
    """Minimal in-memory mirror implementing SessionMirrorProtocol."""

    def __init__(self):
        self._by_session = {}
        self._lock = threading.Lock()

    def append(self, session_id, records):
        with self._lock:
            self._by_session.setdefault(session_id, []).extend(records)

    def load(self, session_id):
        with self._lock:
            return list(self._by_session.get(session_id, []))

    def list_sessions(self, *, user_id=None):
        with self._lock:
            return [{"session_id": sid} for sid in self._by_session]


class _SlowMirror(_RecordingMirror):
    """Mirror whose append blocks, to prove the local turn is never delayed."""

    def __init__(self, delay):
        super().__init__()
        self._delay = delay

    def append(self, session_id, records):
        time.sleep(self._delay)
        super().append(session_id, records)


def test_recording_mirror_satisfies_protocol():
    """A simple mirror is recognised by the runtime-checkable protocol."""
    assert isinstance(_RecordingMirror(), SessionMirrorProtocol)


def test_no_mirror_zero_overhead():
    """Unset mirror → no writer thread, no behaviour change."""
    before = threading.active_count()
    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d)
        assert store._mirror_writer is None
        assert store.add_message("s1", "user", "hello") is True
        # flush_mirror is a no-op that returns True when unconfigured.
        assert store.flush_mirror() is True
    assert threading.active_count() == before


def test_mirror_receives_appended_records():
    """A configured mirror receives each persisted message (with tool calls)."""
    mirror = _RecordingMirror()
    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d, mirror=mirror)
        try:
            store.add_message("s1", "user", "refactor the parser")
            store.add_message(
                "s1",
                "assistant",
                "",
                tool_calls=[{"id": "c1", "type": "function",
                             "function": {"name": "edit", "arguments": "{}"}}],
            )
            assert store.flush_mirror(timeout=5.0) is True
        finally:
            store.close_mirror()

    records = mirror.load("s1")
    assert len(records) == 2
    assert records[0]["role"] == "user"
    assert records[0]["content"] == "refactor the parser"
    # Every record is id- and session-tagged for conflict-free mirroring.
    assert records[0]["id"]
    assert records[0]["session_id"] == "s1"
    # Tool calls survive the mirror hop (schema is tool-call aware).
    assert records[1]["tool_calls"][0]["id"] == "c1"


def test_mirror_appends_async_nonblocking():
    """A slow/outaged mirror never delays or fails the local turn."""
    slow = _SlowMirror(delay=0.5)
    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d, mirror=slow)
        try:
            start = time.time()
            ok = store.add_message("s1", "user", "hi")
            elapsed = time.time() - start
            # Local write returns immediately, well under the mirror's delay.
            assert ok is True
            assert elapsed < 0.3
            # Local history is durable regardless of mirror latency.
            assert store.get_chat_history("s1") == [
                {"role": "user", "content": "hi"}
            ]
            # The record still flushes to the mirror eventually.
            assert store.flush_mirror(timeout=5.0) is True
            assert len(slow.load("s1")) == 1
        finally:
            store.close_mirror()


def test_mirror_failure_does_not_break_local_write():
    """A mirror that always raises must not affect local persistence."""

    class _BrokenMirror:
        def append(self, session_id, records):
            raise RuntimeError("mirror down")

        def load(self, session_id):
            return []

        def list_sessions(self, *, user_id=None):
            return []

    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d, mirror=_BrokenMirror())
        try:
            assert store.add_message("s1", "user", "hello") is True
            # Give the background writer time to exhaust its retries + log.
            store.flush_mirror(timeout=5.0)
            assert store.get_chat_history("s1") == [
                {"role": "user", "content": "hello"}
            ]
        finally:
            store.close_mirror()


def test_set_chat_history_reaches_mirror():
    """Whole-transcript replacement (Session save_state path) is mirrored too."""
    mirror = _RecordingMirror()
    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d, mirror=mirror)
        try:
            assert store.set_chat_history(
                "s1",
                [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ],
            ) is True
            assert store.flush_mirror(timeout=5.0) is True
        finally:
            store.close_mirror()

    records = mirror.load("s1")
    assert [r["content"] for r in records] == ["hi", "hello"]
    assert all(r["session_id"] == "s1" and r["id"] for r in records)


def test_enqueue_after_close_is_dropped_not_stranded():
    """Records enqueued after close_mirror() are dropped-to-log, not stranded."""
    mirror = _RecordingMirror()
    with tempfile.TemporaryDirectory() as d:
        store = DefaultSessionStore(session_dir=d, mirror=mirror)
        store.add_message("s1", "user", "before close")
        assert store.flush_mirror(timeout=5.0) is True
        store.close_mirror()

        # Reused after close: local write must still succeed and flush is a
        # no-op that returns True; the mirror never receives the post-close
        # record (dropped-to-log, not silently queued with no consumer).
        assert store.add_message("s1", "user", "after close") is True
        assert store.flush_mirror(timeout=1.0) is True

    assert [r["content"] for r in mirror.load("s1")] == ["before close"]


def test_failed_construction_leaks_no_thread():
    """A construction that fails after makedirs must not leak a mirror thread."""
    import os

    mirror = _RecordingMirror()
    with tempfile.TemporaryDirectory() as d:
        # A path whose parent is a file cannot be created as a directory, so
        # os.makedirs raises before the mirror writer would be started.
        bad_parent = os.path.join(d, "afile")
        with open(bad_parent, "w") as f:
            f.write("x")
        bad_dir = os.path.join(bad_parent, "sessions")

        before = threading.active_count()
        with pytest.raises(OSError):
            DefaultSessionStore(session_dir=bad_dir, mirror=mirror)
        # No idle daemon thread left behind by the failed construction.
        assert threading.active_count() == before
