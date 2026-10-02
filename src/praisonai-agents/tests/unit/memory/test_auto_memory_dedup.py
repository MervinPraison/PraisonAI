"""Preview and failed writes must not consume automatic memory deduplication."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

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


@pytest.mark.parametrize("message, filename, count_key", [
    ("I prefer concise explanations.", "long_term.json", "long_term_count"),
    ("My name is Alice.", "entities.json", "entity_count"),
])
def test_real_file_write_failure_is_reported_and_retryable(tmp_path, monkeypatch, message, filename, count_key):
    from praisonaiagents.memory import file_memory
    memory = FileMemory(user_id="io-failure", base_path=tmp_path)
    auto = AutoMemory(memory)
    original_replace = file_memory.os.replace

    def fail_destination(source, destination):
        if str(destination).endswith(filename):
            raise OSError("temporary destination failure")
        return original_replace(source, destination)

    monkeypatch.setattr(file_memory.os, "replace", fail_destination)
    with pytest.raises(OSError):
        auto.process_interaction(message)
    assert memory.get_stats()[count_key] == 0
    monkeypatch.setattr(file_memory.os, "replace", original_replace)
    assert auto.process_interaction(message)
    assert auto.process_interaction(message) == []
    reopened = FileMemory(user_id="io-failure", base_path=tmp_path)
    assert reopened.get_stats()[count_key] == 1


def test_partial_retry_does_not_duplicate_successful_records(tmp_path, monkeypatch):
    memory = FileMemory(user_id="partial", base_path=tmp_path)
    auto = AutoMemory(memory)
    original_add = memory.add_long_term
    calls = []

    def fail_second(content, **kwargs):
        calls.append(content)
        if len(calls) == 2:
            raise OSError("second write failed")
        return original_add(content, **kwargs)

    monkeypatch.setattr(memory, "add_long_term", fail_second)
    message = "I prefer concise explanations. I like examples."
    with pytest.raises(OSError, match="second write failed"):
        auto.process_interaction(message)
    monkeypatch.setattr(memory, "add_long_term", original_add)
    # A retry must finish the original extraction, even if extraction changes.
    def unexpected_extract(text):
        raise AssertionError("retry re-extracted a partially stored interaction")

    monkeypatch.setattr(auto.extractor, "extract", unexpected_extract)
    assert auto.process_interaction(message)
    assert auto.process_interaction(message) == []
    reopened = FileMemory(user_id="partial", base_path=tmp_path)
    contents = [item.content for item in reopened.get_long_term()]
    assert sorted(contents) == ["concise explanations", "examples"]


def test_pending_preview_mutation_does_not_change_retry(tmp_path, monkeypatch):
    memory = FileMemory(user_id="preview-pending", base_path=tmp_path)
    auto = AutoMemory(memory)
    original = memory.add_long_term
    calls = []
    def fail_second(content, **kwargs):
        calls.append(content)
        if len(calls) == 2:
            raise OSError("partial outage")
        return original(content, **kwargs)
    monkeypatch.setattr(memory, "add_long_term", fail_second)
    text = "I prefer concise explanations. I like examples."
    with pytest.raises(OSError):
        auto.process_interaction(text)
    preview = auto.process_interaction(text, store=False)
    preview[1]["content"] = "caller mutation"
    preview.clear()
    monkeypatch.setattr(memory, "add_long_term", original)
    assert auto.process_interaction(text)
    assert sorted(item.content for item in memory.get_long_term()) == ["concise explanations", "examples"]


def test_concurrent_identical_calls_store_once(tmp_path, monkeypatch):
    memory = FileMemory(user_id="concurrent", base_path=tmp_path)
    auto = AutoMemory(memory)
    original_add = memory.add_long_term
    first_entered, release = Event(), Event()
    calls = []

    def blocked_first(content, **kwargs):
        calls.append(content)
        if len(calls) == 1:
            first_entered.set()
            assert release.wait(5)
        return original_add(content, **kwargs)

    monkeypatch.setattr(memory, "add_long_term", blocked_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(auto.process_interaction, "I prefer concise explanations.")
        assert first_entered.wait(5)
        second = pool.submit(auto.process_interaction, "I prefer concise explanations.")
        try:
            second.result(timeout=1)
        except TimeoutError:
            pass
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    reopened = FileMemory(user_id="concurrent", base_path=tmp_path)
    assert reopened.get_stats()["long_term_count"] == 1
