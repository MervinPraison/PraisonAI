from unittest.mock import MagicMock

import pytest

from praisonaiagents.session import SqliteTranscriptStore
from praisonai_bot.bots._session import BotSessionManager


@pytest.mark.asyncio
async def test_failed_sqlite_write_keeps_live_history(tmp_path, monkeypatch):
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    manager = BotSessionManager(store=store, platform="test")
    key = manager._session_key("user")
    assert store.set_chat_history(key, [{"role": "user", "content": "old"}])
    agent = MagicMock()
    agent.chat_history = []

    def chat(prompt):
        agent.chat_history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "answer"},
        ])
        return "answer"

    agent.chat.side_effect = chat
    monkeypatch.setattr(store, "_write_row", lambda *args, **kwargs: False)
    assert await manager.chat(agent, "user", "new") == "answer"
    assert manager.warm_sessions()[0].flushed is False
    expected = ["old", "new", "answer"]
    assert [x["content"] for x in manager._load_history("user")] == expected
    assert [x["content"] for x in manager.export_history("user")] == expected
    assert [x["content"] for x in store.get_chat_history(key)] == ["old"]


def test_failed_seed_write_keeps_live_history(tmp_path, monkeypatch):
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    manager = BotSessionManager(store=store, platform="test")
    assert store.set_chat_history(manager._persist_key("user"), [{"role": "user", "content": "old"}])
    monkeypatch.setattr(store, "_write_row", lambda *args, **kwargs: False)
    manager.seed_history("user", [{"role": "user", "content": "new"}])
    assert manager.warm_sessions()[0].flushed is False
    assert manager.export_history("user") == [{"role": "user", "content": "new"}]


@pytest.mark.parametrize("failed_operation", ["clear", "add"])
def test_legacy_store_false_stops_fallback_write(failed_operation):
    class LegacyStore:
        def __init__(self):
            self.added = []

        def clear_session(self, key):
            return False if failed_operation == "clear" else None

        def add_message(self, key, role, content, metadata):
            self.added.append(content)
            return False if failed_operation == "add" else None

    store = LegacyStore()
    manager = BotSessionManager(store=store)
    manager._save_history("user", [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}])
    assert manager.warm_sessions()[0].flushed is False
    assert store.added == ([] if failed_operation == "clear" else ["one"])
