"""Memory text preservation and failed-save snapshot regressions."""

import pytest

from types import SimpleNamespace
from unittest.mock import MagicMock

from praisonaiagents.memory.file_memory import FileMemory


def test_memory_prompt_preserves_all_text_parts():
    from praisonaiagents.agent.tool_execution import _memory_prompt_text

    assert _memory_prompt_text([
        {"type": "text", "text": "first"},
        {"type": "image_url", "text": "attachment"},
        {"type": "text", "text": 42},
        {"type": "text", "text": "second"},
    ]) == "first\nsecond"


@pytest.mark.parametrize("attachment_kind", ["text_file", "text_part"])
def test_chat_memory_excludes_ephemeral_text_attachments(tmp_path, monkeypatch, attachment_kind):
    from praisonaiagents import Agent
    from praisonaiagents.agent.tool_execution import _memory_prompt_text

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = Agent(name="attachment-test", instructions="Test", llm="gpt-4o-mini")
    agent._using_custom_llm = False
    document = "private attachment contents"
    if attachment_kind == "text_file":
        path = tmp_path / "document.txt"
        path.write_text(document, encoding="utf-8")
        attachment = str(path)
    else:
        attachment = {"type": "text", "text": document}
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content="ok", reasoning_content=None))])
    model = MagicMock(return_value=completion)
    monkeypatch.setattr(agent, "_chat_completion", model)
    monkeypatch.setattr(agent, "_execute_callback_and_display", MagicMock())
    monkeypatch.setattr(agent, "_persist_message", MagicMock())
    captured = []

    def after(prompt, response, start_time):
        captured.append(_memory_prompt_text(prompt))
        return response

    monkeypatch.setattr(agent, "_trigger_after_agent_hook", after)
    result = agent._chat_impl(
        prompt="remember my preference", temperature=1.0, tools=None,
        output_json=None, output_pydantic=None, reasoning_steps=False, stream=False,
        task_name=None, task_description=None, task_id=None, config=None,
        force_retrieval=False, skip_retrieval=True, attachments=[attachment],
        _trace_emitter=MagicMock(),
    )
    assert result == "ok"
    assert document in str(model.call_args.args[0])
    assert captured == ["remember my preference"]


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
