"""Regression coverage for Ollama tool-result references on async paths."""

from types import SimpleNamespace

import pytest

import praisonaiagents.llm.llm as llm_module
from praisonaiagents.llm.llm import LLM


def test_ollama_chaining_preserves_exact_tool_results():
    llm = LLM.__new__(LLM)
    llm._provider_adapter = None
    mapping = {
        "lookup": {"city": "Paris", "temperature": -5.5},
        "list_items": ["a", 2],
        "text": "Paris: 21C sunny",
    }

    assert llm._resolve_ollama_chained_args(
        {
            "first": "lookup",
            "second": "list_items",
            "third": "text",
        },
        mapping,
    ) == {
        "first": {"city": "Paris", "temperature": -5.5},
        "second": ["a", 2],
        "third": "Paris: 21C sunny",
    }


def test_ollama_chaining_records_none_and_structured_results():
    llm = LLM.__new__(LLM)
    llm._provider_adapter = None
    mapping = {}

    llm._record_ollama_tool_result(mapping, "empty", None)
    llm._record_ollama_tool_result(mapping, "structured", {"ok": True})

    assert mapping == {"empty": None, "structured": {"ok": True}}


def test_ollama_chaining_does_not_record_error_payloads():
    llm = LLM.__new__(LLM)
    llm._provider_adapter = None
    mapping = {}

    llm._record_ollama_tool_result(mapping, "failed", {"error": "failed: 42"})
    llm._record_ollama_tool_result(mapping, "failed-list", [{"error": "failed"}])

    assert mapping == {}


@pytest.mark.asyncio
async def test_async_ollama_resolves_same_turn_tool_result_references(monkeypatch):
    class Response(SimpleNamespace):
        def __getitem__(self, key):
            return getattr(self, key)

    class Choice(SimpleNamespace):
        def __getitem__(self, key):
            return getattr(self, key)

    llm = LLM.__new__(LLM)
    llm.model = "ollama/llama3"
    llm.verbose = False
    llm.self_reflect = False
    llm.reasoning_steps = False
    llm._console = None
    llm.max_iter = 4
    llm._provider_adapter = SimpleNamespace(
        handle_empty_response_with_tools=lambda context: False,
        supports_streaming=lambda: False,
        supports_streaming_with_tools=lambda: False,
        recover_tool_calls_from_text=lambda text, tools: [],
        should_summarize_tools=lambda iteration: False,
    )
    llm._build_messages = lambda **kwargs: ([], kwargs["prompt"])
    llm._format_tools_for_litellm = lambda tools: [{"type": "function"}]
    llm._supports_responses_api = lambda: False
    llm._is_ollama_provider = lambda: True
    llm._build_completion_params = lambda **kwargs: kwargs
    llm._serialize_tool_calls = lambda calls: calls
    llm._extract_tool_call_info = lambda call, is_ollama: (
        call["function"]["name"],
        {} if call["function"]["name"] == "first" else {"value": "first"},
        call["id"],
    )
    llm._validate_and_filter_ollama_arguments = lambda name, args, tools: args
    llm._format_ollama_tool_result_message = (
        lambda name, result: {"role": "user", "content": str(result)}
    )
    llm._record_finish_reason = lambda response: None

    responses = [
        Response(
            choices=[
                Choice(
                    message={
                        "content": "use tools",
                        "tool_calls": [
                            {"id": "call-1", "function": {"name": "first"}},
                            {"id": "call-2", "function": {"name": "second"}},
                        ],
                    }
                )
            ]
        ),
        Response(
            choices=[Choice(message={"content": "final answer", "tool_calls": []})]
        ),
        Response(
            choices=[Choice(message={"content": "final answer", "tool_calls": []})]
        ),
    ]

    async def completion(**kwargs):
        return responses.pop(0)

    llm._acompletion_with_retry = completion
    seen = []

    async def dispatch(execute_tool_fn, function_name, arguments, tool_call_id, iteration_index):
        seen.append((function_name, arguments))
        return 3 if function_name == "first" else 9

    monkeypatch.setattr(llm_module, "_dispatch_async_tool", dispatch)

    result = await llm.get_response_async(
        "question",
        tools=[lambda: None],
        execute_tool_fn=lambda *args: None,
        stream=False,
    )

    assert result == "final answer"
    assert seen == [("first", {}), ("second", {"value": 3})]
