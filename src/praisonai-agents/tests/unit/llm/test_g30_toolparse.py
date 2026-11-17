"""G-30 (toolparse): one copy of a helper llm.py, openai_client.py and tool_execution.py shared (G-30)."""

from praisonaiagents.llm import _helpers


def test_tool_parse_error_message_is_one_function():
    from praisonaiagents.agent import tool_execution
    from praisonaiagents.llm.llm import LLM

    assert tool_execution.tool_parse_error_message is _helpers.tool_parse_error_message
    assert LLM._tool_parse_error_message is _helpers.tool_parse_error_message
    msg = _helpers.tool_parse_error_message("search", "call_1")
    assert msg["role"] == "tool" and msg["tool_call_id"] == "call_1"
    assert "'search'" in msg["content"] and "NOT executed" in msg["content"]
