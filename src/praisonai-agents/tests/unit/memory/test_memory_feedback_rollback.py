"""Memory text preservation and failed-save snapshot regressions."""

import pytest

from praisonaiagents.memory.file_memory import FileMemory


def test_memory_prompt_preserves_all_text_parts():
    from praisonaiagents.agent.tool_execution import _memory_prompt_text

    assert _memory_prompt_text([
        {"type": "text", "text": "first"},
        {"type": "image_url", "text": "attachment"},
        {"type": "text", "text": 42},
        {"type": "text", "text": "second"},
    ]) == "first\nsecond"


@pytest.mark.parametrize("kind", ["long_term", "entity"])
def test_save_exception_restores_memory_snapshot(tmp_path, monkeypatch, kind):
    memory = FileMemory(user_id="rollback", base_path=tmp_path)
    if kind == "long_term":
        memory.add_long_term("original")
        write = lambda: memory.add_long_term("new")
        save = "_save_long_term"
    else:
        memory.add_entity("original", "person", attributes={"state": "old"})
        write = lambda: memory.add_entity("original", "person", attributes={"state": "new"})
        save = "_save_entities"
    field = "long_term" if kind == "long_term" else "entities"
    before = memory.export()[field]
    error = OSError("injected save failure")

    def fail():
        raise error

    monkeypatch.setattr(memory, save, fail)
    with pytest.raises(OSError) as caught:
        write()
    assert caught.value is error
    assert memory.export()[field] == before
    assert FileMemory(user_id="rollback", base_path=tmp_path).export()[field] == before
