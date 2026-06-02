"""Regression tests for sync SQLite query parameterization."""

from praisonai.persistence.conversation.sync_sqlite import SyncSQLiteConversationStore


class _TestSyncSQLiteConversationStore(SyncSQLiteConversationStore):
    def close(self):
        pass


class _Cursor:
    def fetchall(self):
        return []


class _Connection:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        return _Cursor()

    def close(self):
        pass


def test_list_sessions_uses_bound_limit_and_offset(monkeypatch):
    store = _TestSyncSQLiteConversationStore(path=":memory:")
    store._initialized = True
    conn = _Connection()
    monkeypatch.setattr(store, "_get_connection", lambda: conn)

    store.list_sessions(user_id="u1", agent_id="a1", limit=5, offset=2)

    assert "LIMIT ?" in conn.query
    assert "OFFSET ?" in conn.query
    assert conn.params == ["u1", "a1", 5, 2]


def test_get_messages_uses_bound_limit_and_offset(monkeypatch):
    store = _TestSyncSQLiteConversationStore(path=":memory:")
    store._initialized = True
    conn = _Connection()
    monkeypatch.setattr(store, "_get_connection", lambda: conn)

    store.get_messages(session_id="s1", limit=10, offset=3)

    assert "LIMIT ?" in conn.query
    assert "OFFSET ?" in conn.query
    assert conn.params == ["s1", 10, 3]
