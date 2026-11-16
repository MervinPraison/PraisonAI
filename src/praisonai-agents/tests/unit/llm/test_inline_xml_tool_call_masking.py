"""Non-streaming XML tool-call recovery masks fenced code (issue #6286).

The tool loop in ``llm.py`` used to run a second, unmasked ``<tool_call>``
parser over the raw reply for every provider, so a call a hosted model only
*showed* inside a code fence was executed. The model call is stubbed;
nothing leaves the machine.
"""
import pytest

pytest.importorskip("litellm")

from praisonaiagents.llm.llm import LLM  # noqa: E402

MODEL = "openrouter/meta-llama/llama-3.1-70b-instruct"  # hosted -> DefaultAdapter
CALL = '<tool_call>{"name": "delete_file", "arguments": {"path": "x"}}</tool_call>'


def _run(monkeypatch, first_reply):
    import litellm
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    replies = [first_reply, "done"]
    calls = []

    def fake(*a, **k):
        text = replies.pop(0) if replies else "done"
        return litellm.ModelResponse(model=k.get("model"), usage={
            "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            choices=[{"index": 0, "finish_reason": "stop",
                      "message": {"role": "assistant", "content": text}}])

    monkeypatch.setattr(LLM, "_completion_with_retry", lambda self, **k: fake(**k))

    def delete_file(path: str) -> str:
        """Delete a file."""
        calls.append(path)
        return "deleted"

    LLM(model=MODEL).get_response(
        "How do I call delete_file?", tools=[delete_file],
        execute_tool_fn=lambda name, args, *a, **k: delete_file(**args),
        verbose=False, stream=False)
    return calls


def test_fenced_example_tool_call_is_not_executed(monkeypatch):
    reply = f"Here is an example:\n```\n{CALL}\n```\nThat is how you call it."
    assert _run(monkeypatch, reply) == []


def test_unfenced_tool_call_is_still_recovered(monkeypatch):
    assert _run(monkeypatch, CALL) == ["x"]


def test_fence_with_inline_delimiter_still_masks_call(monkeypatch):
    reply = f"Example:\n```xml\n<!-- literal ``` delimiter -->\n{CALL}\n```\nDone."
    assert _run(monkeypatch, reply) == []


def test_call_after_crlf_closed_fence_is_recovered(monkeypatch):
    example = CALL.replace('"x"', '"example"')
    reply = f"Example:\r\n```\r\n{example}\r\n```\r\nNow: {CALL}"
    assert _run(monkeypatch, reply) == ["x"]


def test_call_after_inline_code_span_is_recovered(monkeypatch):
    reply = f"The format is ```xml```.\n{CALL}"
    assert _run(monkeypatch, reply) == ["x"]


def test_inline_code_span_example_is_not_executed(monkeypatch):
    reply = f"Example: ```{CALL}``` is the format."
    assert _run(monkeypatch, reply) == []


def test_plain_json_answer_is_not_executed(monkeypatch):
    reply = '{"name": "delete_file", "arguments": {"path": "x"}, "format": "<tool_call>"}'
    assert _run(monkeypatch, reply) == []


def test_unadvertised_json_name_not_recovered_by_local_salvage():
    from praisonaiagents.llm.adapters import _recover_json_tool_calls
    tools = [{"type": "function", "function": {"name": "search"}}]
    assert _recover_json_tool_calls('{"name": "delete_file", "arguments": {}}', tools) is None
    assert _recover_json_tool_calls('{"name": "search", "arguments": {}}', tools)
