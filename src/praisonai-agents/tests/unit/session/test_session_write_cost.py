"""G-15: the session store must not stream JSON token by token.

``DefaultSessionStore`` rewrites the session file on every message. It did so
with ``json.dump(..., indent=2)``, which runs the pure-Python encoder and
issues one ``write()`` per token: ~3.9M writes for 100 messages added to a
2,000-message session, 87% of ``add_message`` time (1.7 ms/message at 250
messages, 16 ms at 2,000). Encoding to one string first writes the same bytes
in one call.
"""

import io
import json

import pytest

from praisonaiagents.session.store import DefaultSessionStore


class _CountingStream(io.StringIO):
    def __init__(self):
        super().__init__()
        self.writes = 0

    def write(self, s):
        self.writes += 1
        return super().write(s)


def _sample(n=300):
    return {
        "session_id": "s",
        "messages": [{"role": "user" if i % 2 else "assistant", "content": f"m{i} ü", "metadata": {}}
                     for i in range(n)],
        "metadata": {"k": [1, 2, 3]},
    }


def test_dump_writes_once_with_unchanged_bytes(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    stream = _CountingStream()
    data = _sample()
    store._dump_session_json(data, stream)
    assert stream.writes == 1
    # On-disk format is unchanged: indent=2, non-ASCII kept as-is.
    assert stream.getvalue() == json.dumps(data, indent=2, ensure_ascii=False)


def test_hierarchy_snapshot_dump_writes_once_with_unchanged_bytes(tmp_path):
    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
    store = HierarchicalSessionStore(session_dir=str(tmp_path))
    stream = _CountingStream()
    data = dict(_sample(), snapshot_storage={"v": 1})
    store._dump_session_json(data, stream)
    assert stream.writes == 1
    assert stream.getvalue() == json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def test_session_files_round_trip_and_old_files_still_load(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(20):
        assert store.add_message("sess", "user" if i % 2 else "assistant", f"hello {i}")
    path = store._get_session_path("sess")
    on_disk = open(path, encoding="utf-8").read()
    assert on_disk == json.dumps(json.loads(on_disk), indent=2, ensure_ascii=False)

    # A file written the old way (json.dump streaming) loads identically.
    legacy = DefaultSessionStore(session_dir=str(tmp_path))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(json.loads(on_disk), fh, indent=2, ensure_ascii=False)
    history = legacy.get_chat_history("sess")
    assert [m["content"] for m in history][-3:] == ["hello 17", "hello 18", "hello 19"]
