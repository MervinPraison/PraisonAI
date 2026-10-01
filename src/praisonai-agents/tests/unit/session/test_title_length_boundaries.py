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
