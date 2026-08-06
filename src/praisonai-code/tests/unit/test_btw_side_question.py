"""Tests for the ``/btw`` side-question command (issue #3735).

``/btw <question>`` answers a side question from a parallel, throwaway
context so the main conversation's history and momentum stay untouched.

Key guarantees under test:
- The main ``_conversation_history`` is byte-identical after ``/btw``.
- The side question runs against a *separate* throwaway agent, never the
  main agent, so the main turn is never derailed.
- ``/btw --keep`` records exactly one lightweight note in the main history.
- The side agent is read-only (built with no tools).
"""

import copy

from praisonai_code.cli.interactive.repl import InteractiveREPL, REPLConfig


class _StubIO:
    """Minimal PraisonIO stand-in capturing rendered output."""

    class _Config:
        pretty = False
        multiline_mode = False

    def __init__(self):
        self.console = None
        self.config = self._Config()
        self.messages = []

    def add_commands(self, commands):
        pass

    def info(self, message):
        self.messages.append(("info", message))

    def success(self, message):
        self.messages.append(("success", message))

    def tool_error(self, message):
        self.messages.append(("error", message))

    def tool_warning(self, message):
        self.messages.append(("warning", message))

    def print_assistant_start(self):
        pass

    def print_assistant_response(self, response):
        self.messages.append(("assistant", response))

    def print_help(self, commands):
        pass


def _make_repl():
    repl = InteractiveREPL(config=REPLConfig(model="gpt-4o-mini"))
    repl.io = _StubIO()
    return repl


class _RecordingAgent:
    """Fake side agent that records the prompt it received."""

    def __init__(self):
        self.prompts = []

    def start(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return "REDIS_TLS_URL enables TLS for the Redis connection."


def test_btw_answers_without_touching_main_history(monkeypatch, capsys):
    repl = _make_repl()
    # Seed a realistic main conversation.
    repl._conversation_history = [
        {"role": "user", "content": "refactor the auth module"},
        {"role": "assistant", "content": "Working on it..."},
    ]
    before = copy.deepcopy(repl._conversation_history)

    side_agent = _RecordingAgent()
    monkeypatch.setattr(repl, "_build_side_agent", lambda: side_agent)

    repl._handle_command("/btw what does REDIS_TLS_URL do here?")

    # Main transcript must be byte-identical after a side question.
    assert repl._conversation_history == before
    # The answer was actually rendered as a distinct [btw] block.
    assert "[btw] REDIS_TLS_URL enables TLS" in capsys.readouterr().out
    # The side question actually ran against the throwaway agent.
    assert side_agent.prompts
    assert "REDIS_TLS_URL" in side_agent.prompts[0]


def test_btw_uses_separate_agent_not_main(monkeypatch):
    """The main agent must never be invoked for a side question."""
    repl = _make_repl()

    class _MainAgentSentinel:
        def start(self, prompt):  # pragma: no cover - must never run
            raise AssertionError("main agent must not run for /btw")

    repl._agent = _MainAgentSentinel()

    side_agent = _RecordingAgent()
    monkeypatch.setattr(repl, "_build_side_agent", lambda: side_agent)

    repl._handle_command("/btw quick question")

    assert side_agent.prompts  # side agent ran
    # Main agent untouched (still the sentinel, never replaced).
    assert isinstance(repl._agent, _MainAgentSentinel)


def test_btw_keep_records_single_note(monkeypatch):
    repl = _make_repl()
    repl._conversation_history = [{"role": "user", "content": "main task"}]

    side_agent = _RecordingAgent()
    monkeypatch.setattr(repl, "_build_side_agent", lambda: side_agent)

    repl._handle_command("/btw --keep how do I run tests?")

    # Exactly one lightweight note appended (the original plus one).
    assert len(repl._conversation_history) == 2
    note = repl._conversation_history[-1]
    assert note["role"] == "note"
    assert note["content"] == "[btw] how do I run tests?"


def test_btw_keep_only_parsed_as_leading_option(monkeypatch):
    """A later '--keep' is question text, not the flag."""
    repl = _make_repl()
    side_agent = _RecordingAgent()
    monkeypatch.setattr(repl, "_build_side_agent", lambda: side_agent)

    repl._handle_command("/btw what does --keep mean?")

    # No note recorded: --keep was NOT treated as the flag here.
    assert repl._conversation_history == []
    # The full question (including "--keep") reached the side agent.
    assert side_agent.prompts
    assert "--keep mean?" in side_agent.prompts[0]


def test_btw_empty_question_warns(monkeypatch):
    repl = _make_repl()
    before = copy.deepcopy(repl._conversation_history)

    called = {"built": False}

    def _fail_build():
        called["built"] = True
        raise AssertionError("should not build an agent for empty question")

    monkeypatch.setattr(repl, "_build_side_agent", _fail_build)

    repl._handle_command("/btw   ")

    assert repl._conversation_history == before
    assert not called["built"]
    assert any(kind == "warning" for kind, _ in repl.io.messages)


def test_btw_side_agent_is_read_only(monkeypatch):
    """The throwaway agent is built with no tools (read-only)."""
    captured = {}

    class _FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self, prompt):
            return "ok"

    import praisonaiagents

    monkeypatch.setattr(praisonaiagents, "Agent", _FakeAgent)

    repl = _make_repl()
    agent = repl._build_side_agent()

    assert isinstance(agent, _FakeAgent)
    # Read-only: no tools wired into the side agent.
    assert "tools" not in captured
    # Autonomy is explicitly disabled so it can never run the tool-using loop.
    assert captured.get("autonomy") is False


def test_btw_materializes_streaming_generator(monkeypatch, capsys):
    """A streaming (generator) response is consumed, not str()'d to a repr."""

    class _StreamingAgent:
        def start(self, prompt, **kwargs):
            # Emulate a TTY streaming agent: yield chunks lazily.
            def _gen():
                yield "REDIS_TLS_URL "
                yield "enables TLS"

            return _gen()

    repl = _make_repl()
    monkeypatch.setattr(repl, "_build_side_agent", lambda: _StreamingAgent())

    repl._handle_command("/btw what is REDIS_TLS_URL?")

    out = capsys.readouterr().out
    assert "[btw] REDIS_TLS_URL enables TLS" in out
    assert "generator object" not in out
