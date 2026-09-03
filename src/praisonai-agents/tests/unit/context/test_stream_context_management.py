"""Regression tests for issue #4714.

The streaming entry point (``_start_stream_impl``) used to build the outbound
message list and send it to the provider without ever calling
``_apply_context_management``. A long-running chat therefore replayed its whole
transcript on every streamed turn until the provider rejected the request,
while the non-streaming path (``_chat_impl``) compacted correctly.

These tests drive the OpenAI streaming path with a fake client that captures
the outbound messages and assert that context management runs and bounds the
request.
"""


class _FakeDelta:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, capture):
        self._capture = capture

    def create(self, **kwargs):
        self._capture["messages"] = kwargs.get("messages")
        return iter([_FakeChunk("ok")])


class _FakeChat:
    def __init__(self, capture):
        self.completions = _FakeCompletions(capture)


class _FakeSyncClient:
    def __init__(self, capture):
        self.chat = _FakeChat(capture)


class _FakeOpenAIClient:
    """Minimal stand-in for the internal OpenAI client wrapper."""

    def __init__(self, capture):
        self.sync_client = _FakeSyncClient(capture)

    def build_messages(self, prompt, system_prompt=None, chat_history=None,
                        output_json=None, output_pydantic=None):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": str(prompt)})
        return messages, str(prompt)


def _make_streaming_agent(capture):
    from praisonaiagents import Agent

    def sample_tool(query: str) -> str:
        """A sample tool."""
        return f"Result for {query}"

    # Tools present -> context management auto-enabled (auto_compact, SMART).
    agent = Agent(instructions="You are helpful", tools=[sample_tool])
    agent._using_custom_llm = False
    # ``_openai_client`` is a read-only lazy property backed by the
    # name-mangled ``__openai_client`` attribute; seed it directly.
    agent._Agent__openai_client = _FakeOpenAIClient(capture)
    return agent


class TestStreamingContextManagement:
    def test_streaming_path_invokes_context_management(self):
        """The streamed request must call _apply_context_management (#4714)."""
        capture = {}
        agent = _make_streaming_agent(capture)

        calls = {"n": 0}
        original = agent._apply_context_management

        def _counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        agent._apply_context_management = _counting

        # Seed a long transcript, the way the desktop replays persisted history.
        agent.chat_history = []
        for i in range(500):
            agent.chat_history.append(
                {"role": "user", "content": f"question {i} " * 40}
            )
            agent.chat_history.append(
                {"role": "assistant", "content": f"answer {i} " * 40}
            )

        list(agent._start_stream_impl("final question"))

        assert calls["n"] >= 1, "streaming path never called _apply_context_management"

    def test_streaming_request_is_bounded(self):
        """Outbound message list must be smaller than the raw replayed history."""
        capture = {}
        agent = _make_streaming_agent(capture)

        agent.chat_history = []
        for i in range(500):
            agent.chat_history.append(
                {"role": "user", "content": f"question {i} " * 40}
            )
            agent.chat_history.append(
                {"role": "assistant", "content": f"answer {i} " * 40}
            )
        raw_len = len(agent.chat_history)

        list(agent._start_stream_impl("final question"))

        sent = capture.get("messages")
        assert sent is not None, "no request was sent"
        # Compaction must bound the outbound list well below the raw history.
        assert len(sent) < raw_len, (
            f"outbound messages ({len(sent)}) not bounded below raw history "
            f"({raw_len}) - compaction did not run"
        )
