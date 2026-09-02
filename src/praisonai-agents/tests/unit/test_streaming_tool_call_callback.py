"""
Unit tests for the tool_call display callback firing on the streaming path.

Regression for the issue where the streaming chat path executed accumulated
tool calls inline but never fired ``execute_sync_callback('tool_call', ...)``,
leaving streaming UIs (e.g. the desktop's tool-card pipeline) blind to tool
activity. The non-stream native-tools loop already fires it; the stream branch
did not. See Agent.start(prompt, stream=True, ...).
"""

from types import SimpleNamespace

import praisonaiagents.main as _main


def _delta(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


def _tool_call_delta(index, tc_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=tc_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _make_stub_openai_client():
    """A stub OpenAI client whose stream first requests tool `f`, then answers.

    The first ``create`` call yields tool-call chunks; the follow-up ``create``
    call (after the tool runs) yields a plain text answer.
    """
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return iter([
                _delta(tool_calls=[_tool_call_delta(0, tc_id="call_1", name="f", arguments="{}")]),
            ])
        return iter([_delta(content="done")])

    def build_messages(prompt=None, system_prompt=None, chat_history=None,
                       output_json=None, output_pydantic=None, **_kw):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages, prompt

    sync_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return SimpleNamespace(sync_client=sync_client, build_messages=build_messages)


def test_streaming_fires_tool_call_callback_once():
    from praisonaiagents import Agent

    def f():
        """A trivial tool."""
        return "42"

    saved_sync = dict(_main.sync_display_callbacks)
    events = []
    _main.register_display_callback('tool_call', lambda **kw: events.append(kw), is_async=False)

    try:
        agent = Agent(instructions="test", tools=[f], llm="gpt-4o")
        agent._Agent__openai_client = _make_stub_openai_client()

        chunks = list(agent.start("call f", stream=True))

        # The tool_call callback must fire exactly once for tool `f`.
        f_events = [e for e in events if e.get("tool_name") == "f"]
        assert len(f_events) == 1, f"expected 1 tool_call event for f, got {len(f_events)}"
        assert "done" in "".join(str(c) for c in chunks)
    finally:
        _main.sync_display_callbacks.clear()
        _main.sync_display_callbacks.update(saved_sync)
