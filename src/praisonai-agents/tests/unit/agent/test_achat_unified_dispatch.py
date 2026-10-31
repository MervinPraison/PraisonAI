"""Unit tests for unified achat dispatch (Issue #1703)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents import Agent


def _fake_completion(content: str = "Mock async reply"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, reasoning_content=None))]
    )


@pytest.mark.asyncio
async def test_unified_achat_returns_after_single_dispatch():
    """achat must return after one unified dispatch, not loop forever."""
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    agent._using_custom_llm = False
    agent.self_reflect = False

    mock_unified = AsyncMock(return_value=_fake_completion())

    with patch.object(agent, "_execute_unified_achat_completion", mock_unified), patch.object(
        agent, "_apply_guardrail_with_retry", return_value="Mock async reply"
    ), patch.object(
        agent, "_atrigger_after_agent_hook", new_callable=AsyncMock, return_value="Mock async reply"
    ), patch.object(
        agent, "_execute_callback_and_display"
    ), patch.object(
        agent, "_build_messages", return_value=([{"role": "user", "content": "hi"}], "hi")
    ), patch.object(
        agent, "_persist_message"
    ), patch.object(
        agent, "_format_tools_for_completion", return_value=[]
    ):
        result = await asyncio.wait_for(agent.achat("hi", stream=False), timeout=5)

    assert result == "Mock async reply"
    mock_unified.assert_called_once()


@pytest.mark.asyncio
async def test_unified_achat_completion_uses_execute_tool_async():
    """Async unified dispatch must wire execute_tool_async, not sync execute_tool."""
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    agent._using_custom_llm = False

    mock_dispatcher = MagicMock()
    mock_dispatcher.achat_completion = AsyncMock(return_value=_fake_completion())
    agent._unified_dispatcher = mock_dispatcher

    with patch.object(agent, "_apply_guardrail_with_retry", return_value="ok"), patch.object(
        agent, "_atrigger_after_agent_hook", new_callable=AsyncMock, return_value="ok"
    ), patch.object(agent, "_execute_callback_and_display"), patch.object(
        agent, "_build_messages", return_value=([{"role": "user", "content": "hi"}], "hi")
    ), patch.object(agent, "_persist_message"), patch.object(
        agent, "_format_tools_for_completion", return_value=[]
    ):
        await agent._achat_impl(
            prompt="hi",
            temperature=1.0,
            tools=None,
            output_json=None,
            output_pydantic=None,
            reasoning_steps=False,
            stream=False,
            task_name=None,
            task_description=None,
            task_id=None,
            config=None,
            force_retrieval=False,
            skip_retrieval=True,
            attachments=None,
            _trace_emitter=MagicMock(),
        )

    call_kwargs = mock_dispatcher.achat_completion.call_args[1]
    tool_fn = call_kwargs.get("execute_tool_fn")
    assert tool_fn is not None
    assert getattr(tool_fn, "__name__", "") == "execute_tool_async"


@pytest.mark.asyncio
async def test_achat_completion_resolves_basetool_without_dunder_name():
    """BaseTool instances expose .name but no __name__; dispatch must not crash.

    Regression for issue #3450 where bot ``--browser`` wired ``BrowserBaseTool``
    (a BaseTool instance) and async dispatch raised
    ``'BrowserBaseTool' object has no attribute '__name__'``.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")

    class _BrowserLikeTool:
        name = "browserbase"

        def run(self, **kwargs):
            return "ran"

    browser_tool = _BrowserLikeTool()
    assert not hasattr(browser_tool, "__name__")

    tool_call = SimpleNamespace(
        id="legacy-tool-call-001",
        function=SimpleNamespace(name="browserbase", arguments="{}")
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )

    with patch.object(
        agent, "execute_tool_async", new_callable=AsyncMock, return_value="ran"
    ) as mock_exec:
        results = await agent._achat_completion(response, tools=[browser_tool])

    mock_exec.assert_awaited_once()
    assert mock_exec.await_args[0][0] == "browserbase"
    assert mock_exec.await_args.kwargs["tool_call_id"] == "legacy-tool-call-001"
    assert results is not None


@pytest.mark.asyncio
async def test_execute_tool_async_runs_real_basetool_instance():
    """Full async path must resolve AND invoke a real BaseTool instance.

    Regression for issue #3450: even after dispatch resolves a BaseTool by
    ``.name``, the downstream ``_execute_tool_async_impl`` previously matched
    only on ``__name__`` and then called ``func(**args)`` directly, so a
    BrowserBaseTool-style instance returned ``Function ... not found`` /
    never ran. This test hits the real execute_tool_async (unmocked).
    """
    from praisonaiagents.tools.base import BaseTool

    class _BrowserTool(BaseTool):
        name = "browserbase"
        description = "Browser-like tool"

        def run(self, **kwargs):
            return "navigated"

    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    tool = _BrowserTool()

    result = await agent.execute_tool_async("browserbase", {}, tools_override=[tool])

    assert result == "navigated"


@pytest.mark.asyncio
async def test_execute_tool_async_resolves_aliased_function_name():
    """Async dispatch must resolve a tool by its advertised .name alias.

    A FunctionTool-like object may expose a ``.name`` that differs from the
    wrapped callable's ``__name__``; the model calls the advertised ``.name``,
    so resolution must not short-circuit on ``__name__``.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")

    def _impl(**kwargs):
        return "aliased-ran"

    _impl.name = "advertised_name"

    result = await agent.execute_tool_async(
        "advertised_name", {}, tools_override=[_impl]
    )

    assert result == "aliased-ran"


@pytest.mark.asyncio
async def test_achat_completion_streams_final_response_after_tool_calls():
    """After running tools, the legacy async path must ask the model for a
    final answer instead of failing and returning the raw tool output.

    ``_achat_completion`` used to reference an undefined ``stream`` name and
    ``_get_llm_functions`` (only defined in ``agent.py``), so the follow-up
    completion always raised ``NameError``, which was swallowed and the raw
    tool results were returned.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")

    def lookup(query: str) -> str:
        return "tool output"

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="lookup", arguments='{"query": "x"}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )

    def _chunk(content):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )

    async def _stream():
        for part in ("final ", "answer"):
            yield _chunk(part)

    create = AsyncMock(return_value=_stream())
    fake_client = SimpleNamespace(
        async_client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    final = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="final answer"))]
    )
    process_stream_chunks = MagicMock(return_value=final)

    with patch.object(
        type(agent), "_openai_client", new=fake_client
    ), patch.object(
        agent, "execute_tool_async", new_callable=AsyncMock, return_value="tool output"
    ), patch(
        "praisonaiagents.agent.agent._get_llm_functions",
        return_value={"process_stream_chunks": process_stream_chunks},
    ), patch(
        "praisonaiagents.agent.chat_mixin._get_display_functions"
    ) as display:
        result = await agent._achat_completion(response, tools=[lookup])

    display.return_value.__getitem__.return_value.assert_not_called()
    create.assert_awaited_once()
    assert create.await_args.kwargs["stream"] is True
    process_stream_chunks.assert_called_once()
    assert result == "final answer"


@pytest.mark.asyncio
async def test_achat_completion_follow_up_keeps_conversation_and_skips_empty_chunks():
    """The post-tool follow-up request must keep the original conversation (so
    the final answer still sees the user's question), and stream chunks with no
    ``choices`` (e.g. Azure content-filter annotations) must be skipped rather
    than raising ``IndexError`` and falling back to the raw tool output.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")

    def lookup(query: str) -> str:
        return "tool output"

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="lookup", arguments='{"query": "x"}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )
    conversation = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Look up x and answer in French"},
    ]

    async def _stream():
        yield SimpleNamespace(choices=[])
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="réponse"))]
        )

    create = AsyncMock(return_value=_stream())
    fake_client = SimpleNamespace(
        async_client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    final = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="réponse"))]
    )
    process_stream_chunks = MagicMock(return_value=final)

    with patch.object(
        type(agent), "_openai_client", new=fake_client
    ), patch.object(
        agent, "execute_tool_async", new_callable=AsyncMock, return_value="tool output"
    ), patch(
        "praisonaiagents.agent.agent._get_llm_functions",
        return_value={"process_stream_chunks": process_stream_chunks},
    ), patch(
        "praisonaiagents.agent.chat_mixin._get_display_functions"
    ) as display:
        result = await agent._achat_completion(
            response, tools=[lookup], messages=conversation
        )

    display.return_value.__getitem__.return_value.assert_not_called()
    sent = create.await_args.kwargs["messages"]
    assert sent[: len(conversation)] == conversation
    assert "tool output" in sent[-1]["content"]
    # The caller's list is not mutated.
    assert len(conversation) == 2
    assert result == "réponse"


@pytest.mark.asyncio
async def test_legacy_achat_impl_forwards_conversation_to_tool_follow_up():
    """The legacy ``_achat_impl`` tool branch must pass the conversation to
    ``_achat_completion`` so the follow-up request still has the user's prompt.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    agent._using_custom_llm = False
    agent._use_unified_llm_dispatch = False

    def lookup(query: str) -> str:
        return "tool output"

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="lookup", arguments='{"query": "x"}'),
    )
    tool_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )

    async def _stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="final answer"))]
        )

    create = AsyncMock(side_effect=[tool_response, _stream()])
    fake_client = SimpleNamespace(
        async_client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    final = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="final answer"))]
    )
    prompt_messages = [{"role": "user", "content": "Look up x for me"}]

    with patch.object(type(agent), "_openai_client", new=fake_client), patch.object(
        agent, "execute_tool_async", new_callable=AsyncMock, return_value="tool output"
    ), patch(
        "praisonaiagents.agent.agent._get_llm_functions",
        return_value={"process_stream_chunks": MagicMock(return_value=final)},
    ), patch.object(
        agent, "_atrigger_after_agent_hook", new_callable=AsyncMock, side_effect=lambda p, r, t: r
    ), patch.object(agent, "_execute_callback_and_display"), patch.object(
        agent, "_build_messages", return_value=(list(prompt_messages), "Look up x for me")
    ), patch.object(agent, "_persist_message"), patch.object(
        agent, "_format_tools_for_completion", return_value=[{"type": "function"}]
    ):
        result = await agent._achat_impl(
            prompt="Look up x for me",
            temperature=1.0,
            tools=[lookup],
            output_json=None,
            output_pydantic=None,
            reasoning_steps=False,
            stream=False,
            task_name=None,
            task_description=None,
            task_id=None,
            config=None,
            force_retrieval=False,
            skip_retrieval=True,
            attachments=None,
            _trace_emitter=MagicMock(),
        )

    assert create.await_count == 2
    follow_up = create.await_args_list[1].kwargs["messages"]
    assert {"role": "user", "content": "Look up x for me"} in follow_up
    assert result == "final answer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "follow_up_chunk",
    [
        pytest.param(SimpleNamespace(choices=[]), id="empty-choices"),
        pytest.param(
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]
            ),
            id="choice-without-content",
        ),
    ],
)
async def test_achat_completion_falls_back_when_follow_up_has_no_answer_chunks(follow_up_chunk):
    """A follow-up stream with no answer text (only empty-``choices`` chunks or
    choices without ``delta.content``) must log an error and return the tool
    results, not an empty string.
    """
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")

    def lookup(query: str) -> str:
        return "tool output"

    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="lookup", arguments='{"query": "x"}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )

    async def _stream():
        yield follow_up_chunk

    create = AsyncMock(return_value=_stream())
    fake_client = SimpleNamespace(
        async_client=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    process_stream_chunks = MagicMock()

    with patch.object(type(agent), "_openai_client", new=fake_client), patch.object(
        agent, "execute_tool_async", new_callable=AsyncMock, return_value="tool output"
    ), patch(
        "praisonaiagents.agent.agent._get_llm_functions",
        return_value={"process_stream_chunks": process_stream_chunks},
    ), patch(
        "praisonaiagents.agent.chat_mixin._get_display_functions"
    ) as display:
        result = await agent._achat_completion(response, tools=[lookup])

    display.return_value.__getitem__.return_value.assert_called()
    process_stream_chunks.assert_not_called()
    assert result == "tool output"
