"""Preview and failed writes must not consume automatic memory deduplication."""

import pytest

from praisonaiagents.memory.auto_memory import AutoMemory
from praisonaiagents.memory.file_memory import FileMemory


def test_preview_can_be_repeated_and_then_stored(tmp_path):
    memory = FileMemory(user_id="preview", base_path=tmp_path)
    auto = AutoMemory(memory)
    message = "I prefer concise explanations."
    preview = auto.process_interaction(message, store=False)
    assert preview
    assert memory.get_stats()["long_term_count"] == 0
    assert auto.process_interaction(message, store=False) == preview
    assert auto.process_interaction(message) == preview
    assert memory.get_stats()["long_term_count"] == 1
    assert FileMemory(user_id="preview", base_path=tmp_path).get_stats()["long_term_count"] == 1
    assert auto.process_interaction(message) == []
    assert memory.get_stats()["long_term_count"] == 1


def test_failed_storage_can_be_retried(tmp_path, monkeypatch):
    memory = FileMemory(user_id="retry", base_path=tmp_path)
    auto = AutoMemory(memory)
    original_add = memory.add_long_term

    def fail(*args, **kwargs):
        raise OSError("temporary write failure")

    monkeypatch.setattr(memory, "add_long_term", fail)
    with pytest.raises(OSError, match="temporary write failure"):
        auto.process_interaction("I prefer concise explanations.")
    monkeypatch.setattr(memory, "add_long_term", original_add)
    assert auto.process_interaction("I prefer concise explanations.")
    assert memory.get_stats()["long_term_count"] == 1


def test_successful_storage_remains_deduplicated(tmp_path):
    memory = FileMemory(user_id="success", base_path=tmp_path)
    auto = AutoMemory(memory)
    assert auto.process_interaction("I prefer concise explanations.")
    assert auto.process_interaction("I prefer concise explanations.") == []
    assert memory.get_stats()["long_term_count"] == 1


def test_disabled_call_does_not_consume_interaction(tmp_path):
    memory = FileMemory(user_id="disabled", base_path=tmp_path)
    auto = AutoMemory(memory, enabled=False)
    assert auto.process_interaction("I prefer concise explanations.") == []
    auto.enable()
    assert auto.process_interaction("I prefer concise explanations.")
    assert memory.get_stats()["long_term_count"] == 1
