"""Regression coverage for tool calls returned by the streaming LLM path."""

from types import SimpleNamespace

import praisonaiagents.llm.llm as llm_module
from praisonaiagents.llm.llm import LLM


def test_streaming_tool_call_is_executed_before_follow_up(monkeypatch):
    llm = LLM.__new__(LLM)
    llm.model = "gpt-4o"
    llm.tool_timeout_ms = None
    llm._build_messages = lambda **kwargs: ([], kwargs["prompt"])
    llm._format_tools_for_litellm = lambda tools: [{"type": "function"}]
    llm._supports_streaming_tools = lambda: True
    llm._build_completion_params = lambda **kwargs: kwargs
    llm._process_stream_delta = lambda *args, **kwargs: (
        "",
        [{"id": "call-1", "function": {"name": "lookup", "arguments": "{}"}}],
    )
    llm._is_ollama_provider = lambda: False
    llm._serialize_tool_calls = lambda calls: calls
    llm._extract_tool_call_info = lambda call, is_ollama: (
        "lookup",
        {},
        "call-1",
    )
    llm._register_deferred_if_any = lambda result: None
    llm._create_tool_message = lambda *args: {"role": "tool", "content": "ok"}

    completion_calls = []

    def completion(**kwargs):
        completion_calls.append(kwargs)
        if kwargs["stream"]:
            delta = SimpleNamespace(content=None, tool_calls=[object()])
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])
        message = SimpleNamespace(content="final answer")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    llm._completion_with_retry = completion

    batches = []

    class Executor:
        def execute_batch(self, tool_calls, execute_tool_fn, timeout_ms=None):
            batches.append(tool_calls)
            return [
                SimpleNamespace(
                    error=None,
                    function_name="lookup",
                    result="ok",
                    tool_call_id="call-1",
                    is_ollama=False,
                )
            ]

    monkeypatch.setattr(
        llm_module,
        "create_tool_call_executor",
        lambda parallel=False: Executor(),
    )

    chunks = list(
        llm.get_response_stream(
            "question",
            tools=[lambda: None],
            execute_tool_fn=lambda *args: None,
        )
    )

    assert chunks == ["final answer"]
    assert [call["stream"] for call in completion_calls] == [True, False]
    assert completion_calls[1]["messages"][-1] == {
        "role": "tool",
        "content": "ok",
    }
    assert len(batches) == 1
    assert batches[0][0].function_name == "lookup"
    assert batches[0][0].iteration_index == 0
