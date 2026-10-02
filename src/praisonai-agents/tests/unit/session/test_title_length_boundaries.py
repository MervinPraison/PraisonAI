"""The public title length cap applies to generated and fallback titles."""

import pytest

from praisonaiagents.session.title import generate_title, generate_title_async


@pytest.mark.parametrize("max_length", [0, 1, 2, 3, 4, 60])
@pytest.mark.parametrize("user_msg", ["", "?!.", "A long user request about debugging code"])
@pytest.mark.asyncio
async def test_sync_fallback_in_running_loop_respects_length(user_msg, max_length):
    title = generate_title(user_msg, "Response", max_length=max_length)
    assert len(title) <= max_length
    if max_length == 60:
        assert title


@pytest.mark.parametrize("max_length", [0, 1, 2, 3, 4, 60])
@pytest.mark.parametrize("response", ["A long generated title about Python", None])
@pytest.mark.asyncio
async def test_async_generated_and_fallback_titles_respect_length(monkeypatch, max_length, response):
    import praisonaiagents.llm as llm_module

    class LocalLLM:
        def __init__(self, **kwargs):
            pass

        async def get_response_async(self, **kwargs):
            return response

    monkeypatch.setattr(llm_module, "LLM", LocalLLM)
    title = await generate_title_async("", "Response", llm_model="test", max_length=max_length)
    assert len(title) <= max_length
    if max_length == 60:
        assert title == (response or "Chat Session")


@pytest.mark.parametrize("max_length", [0, -1])
@pytest.mark.asyncio
async def test_nonpositive_cap_skips_model_initialization(monkeypatch, max_length):
    import praisonaiagents.llm as llm_module

    calls = []

    class UnexpectedLLM:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        async def get_response_async(self, **kwargs):
            return "Unneeded title"

    monkeypatch.setattr(llm_module, "LLM", UnexpectedLLM)
    assert await generate_title_async("Question", "Response", max_length=max_length) == ""
    assert generate_title("Question", "Response", max_length=max_length) == ""
    assert calls == []


@pytest.mark.parametrize("user_msg", ["", "?!."])
@pytest.mark.asyncio
async def test_three_character_fallback_keeps_readable_prefix(user_msg):
    assert generate_title(user_msg, "Response", max_length=3) == "Cha"


@pytest.mark.asyncio
async def test_three_character_generated_title_keeps_readable_prefix(monkeypatch):
    import praisonaiagents.llm as llm_module

    class LocalLLM:
        def __init__(self, **kwargs):
            pass

        async def get_response_async(self, **kwargs):
            return "Python debugging"

    monkeypatch.setattr(llm_module, "LLM", LocalLLM)
    assert await generate_title_async("Question", "Response", max_length=3) == "Pyt"
