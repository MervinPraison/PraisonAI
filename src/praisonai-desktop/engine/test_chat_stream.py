"""What the user sees when a turn calls tools.

The chat path had no test at all, which is why this shipped: a turn whose tools
all ran and succeeded was reported to the user as "the engine produced no
output". The published praisonaiagents 1.7.1 ends the stream after running
tools without ever asking the model for its answer, so the generator yields
nothing -- and the engine could not tell that apart from a turn where nothing
happened.

The agent is stubbed. These tests never reach a provider and never need a key:
the point is what the engine does with a given stream, not what a model says.
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_HOME = tempfile.mkdtemp(prefix="praison-chat-test-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ.setdefault("PRAISONAI_KEYCHAIN_SERVICE", "ai.praison.desktop.test")

import server                                            # noqa: E402


class StubAgent:
    """An agent whose stream is whatever the test says it is.

    It records the history it was given, because what the model is shown is the
    thing under test.
    """

    def __init__(self, chunks=(), tools=()):
        self.chunks = list(chunks)
        self.tools = list(tools)
        self.started = 0
        self.chat_history = []
        self.seen_history = None

    def _append_to_chat_history(self, message):
        self.chat_history.append(message)

    def start(self, prompt, stream=True, **kwargs):
        self.started += 1
        self.seen_history = list(self.chat_history)
        # Tools "run" before the model's answer would arrive, exactly as the
        # display callback records them during a real turn.
        for tool in self.tools:
            server._tool_queue().append(tool)
        for chunk in self.chunks:
            yield chunk


def _tool(name="current_time", ok=True, output="2026-08-27 00:13:35"):
    return {"call_id": f"c-{name}", "name": name, "args": {},
            "ok": ok, "output": output, "seconds": 0.01}


class ChatStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(_HOME, ignore_errors=True)

    def setUp(self):
        server._agents.clear()
        server._tool_queue().clear()

    def _install(self, chunks=(), tools=()):
        agent = StubAgent(chunks, tools)
        # _get_agent returns from this cache when the key is present, so this
        # replaces the agent without the real one ever being constructed.
        server._agents["t"] = agent
        server._agents["t\x00notools"] = agent
        return agent

    def _chat(self, prompt="what is the current time"):
        """POST /chat and return the SSE frames as (event, data) pairs."""
        body = json.dumps({"prompt": prompt, "chat_id": "t", "session": "t"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        frames, kind = [], None
        with urllib.request.urlopen(req, timeout=30) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event: "):
                    kind = line[7:]
                elif line.startswith("data: ") and kind:
                    frames.append((kind, json.loads(line[6:] or "{}")))
                    kind = None
        return frames

    # -- the reported bug ------------------------------------------------

    def test_a_turn_whose_tools_ran_is_not_reported_as_no_output(self):
        self._install(chunks=(), tools=[_tool()])
        frames = self._chat()
        kinds = [k for k, _ in frames]
        errors = [d for k, d in frames if k == "error"]
        self.assertTrue(errors, f"no error was reported at all: {kinds}")
        self.assertNotEqual(
            errors[0].get("kind"), "empty",
            "a turn whose tools all ran was reported as producing nothing")
        self.assertEqual(errors[0].get("kind"), "no_answer")

    def test_the_tool_results_are_still_shown_when_the_answer_never_comes(self):
        # The work happened. Losing it is the part the user actually feels.
        self._install(chunks=(), tools=[_tool(output="2026-08-27 00:13:35")])
        frames = self._chat()
        kinds = [k for k, _ in frames]
        self.assertIn("tool_call", kinds, f"the tool call was never shown: {kinds}")
        self.assertIn("tool_result", kinds, f"the tool result was never shown: {kinds}")
        results = [d for k, d in frames if k == "tool_result"]
        self.assertEqual(results[0]["output"], "2026-08-27 00:13:35")

    def test_a_stream_that_yielded_something_first_still_counts_its_tools(self):
        # Every tool-then-die test above uses chunks=(), which is the one path
        # where the loop body never runs -- so the drain inside the loop was
        # never exercised and its discarded return value went unnoticed. One
        # frame of anything is enough to take the other path.
        self._install(chunks=[{"type": "reasoning", "text": "thinking"}], tools=[_tool()])
        frames = self._chat()
        errors = [d for k, d in frames if k == "error"]
        self.assertTrue(errors, "no error was reported")
        self.assertEqual(
            errors[0].get("kind"), "no_answer",
            "a stream that yielded a non-text frame lost its tool count")
        self.assertIn("1 tool call(s)", errors[0]["message"])

    def test_an_empty_text_chunk_does_not_lose_the_tool_count(self):
        self._install(chunks=[""], tools=[_tool()])
        errors = [d for k, d in self._chat() if k == "error"]
        self.assertTrue(errors, "no error was reported")
        self.assertEqual(errors[0].get("kind"), "no_answer")

    def test_tools_are_counted_once_not_twice(self):
        # The queue is drained in two places now. Counting the same event in
        # both would inflate the number the user is shown.
        self._install(chunks=[{"type": "reasoning", "text": "x"}],
                      tools=[_tool("a"), _tool("b")])
        errors = [d for k, d in self._chat() if k == "error"]
        self.assertIn("2 tool call(s)", errors[0]["message"])

    def test_the_message_says_how_many_tools_ran(self):
        self._install(chunks=(), tools=[_tool("a"), _tool("b")])
        errors = [d for k, d in self._chat() if k == "error"]
        self.assertIn("2 tool call(s)", errors[0]["message"])

    # -- the failures that must still look like failures -----------------

    def test_a_turn_that_did_nothing_at_all_is_still_empty(self):
        self._install(chunks=(), tools=())
        errors = [d for k, d in self._chat() if k == "error"]
        self.assertEqual(errors[0].get("kind"), "empty",
                         "a genuinely empty turn must not be excused as no_answer")

    # -- the paths that already worked must keep working -----------------

    def test_a_plain_text_turn_still_streams_and_ends(self):
        self._install(chunks=["The current time ", "is 00:13:35."])
        frames = self._chat()
        kinds = [k for k, _ in frames]
        self.assertIn("delta", kinds)
        self.assertIn("end", kinds)
        self.assertNotIn("error", kinds, f"a good turn reported an error: {kinds}")
        text = "".join(d.get("text", "") for k, d in frames if k == "delta")
        self.assertEqual(text, "The current time is 00:13:35.")

    def test_a_tool_turn_that_does_answer_shows_both(self):
        # The success path drains the tool queue too. This is a regression
        # guard: the drain used to live only in the success branch, and moving
        # it must not have lost it.
        self._install(chunks=["It is 00:13:35."], tools=[_tool()])
        frames = self._chat()
        kinds = [k for k, _ in frames]
        self.assertIn("tool_result", kinds, f"tools vanished on the success path: {kinds}")
        self.assertIn("delta", kinds)
        self.assertIn("end", kinds)
        self.assertNotIn("error", kinds)


class HistoryAcrossSessions(unittest.TestCase):
    """Reopening a chat must not hand the model a blank slate.

    The transcript on disk is what the sidebar renders; the agent's
    chat_history is what the model is shown. Nothing copied one into the other,
    and the agent cache does not survive a restart, a settings change, or the
    tools toggle. So the user saw their whole conversation on screen while the
    model answered "I don't have access to your previous questions."
    """

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        server._agents.clear()
        server._tool_queue().clear()
        # One transcript per test: these persist to disk, so a shared id let
        # one test's turns leak into the next one's replay.
        self.chat = f"revisited-{self._testMethodName}"

    def _say(self, prompt, chunks, tools_on=True):
        agent = StubAgent(chunks)
        key = self.chat if tools_on else self.chat + "\x00notools"
        server._agents[key] = agent
        body = json.dumps({"prompt": prompt, "chat_id": self.chat,
                           "session": self.chat, "tools": tools_on}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
        return agent

    def _roles_and_text(self, agent):
        return [(m["role"], m["content"]) for m in (agent.seen_history or [])]

    def test_a_returning_session_is_given_the_earlier_turns(self):
        self._say("what tools do you have", ["I have current_time."])
        # Navigating away and back drops the cached agent -- as a restart, a
        # settings change or the tools toggle all do.
        server._agents.clear()
        agent = self._say("what were my previous questions", ["You asked about tools."])
        seen = self._roles_and_text(agent)
        self.assertTrue(seen, "the model was given no history at all")
        self.assertIn(("user", "what tools do you have"), seen)
        self.assertIn(("assistant", "I have current_time."), seen)

    def test_the_replay_is_in_order(self):
        self._say("first", ["one"])
        self._say("second", ["two"])
        server._agents.clear()
        agent = self._say("third", ["three"])
        roles = [r for r, _ in self._roles_and_text(agent)]
        texts = [t for _, t in self._roles_and_text(agent)]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"])
        self.assertEqual(texts, ["first", "one", "second", "two"])

    def test_an_agent_that_already_has_history_is_not_replayed_over(self):
        # Mid-session the agent already holds the turns, including tool
        # messages the transcript never stored. Replaying would duplicate them.
        self._say("first", ["one"])
        agent = StubAgent(["two"])
        agent._append_to_chat_history({"role": "user", "content": "first"})
        agent._append_to_chat_history({"role": "assistant", "content": "one"})
        server._agents[self.chat] = agent
        body = json.dumps({"prompt": "second", "chat_id": self.chat,
                           "session": self.chat}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
        self.assertEqual(len(agent.seen_history), 2,
                         f"history was duplicated: {agent.seen_history}")

    def test_toggling_tools_does_not_lose_the_conversation(self):
        # The tools flag keys a different agent for the same session.
        self._say("what tools do you have", ["I have current_time."], tools_on=True)
        agent = self._say("and now", ["Sure."], tools_on=False)
        self.assertIn(("user", "what tools do you have"), self._roles_and_text(agent))

    def test_a_chat_with_no_transcript_starts_clean(self):
        agent = StubAgent(["hi"])
        server._agents["brand-new"] = agent
        body = json.dumps({"prompt": "hello", "chat_id": "brand-new",
                           "session": "brand-new"}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
        self.assertEqual(agent.seen_history, [])

    def test_a_failed_turn_is_not_replayed_as_an_empty_answer(self):
        # A turn that errored leaves nothing useful; feeding an empty
        # assistant message back teaches the model that silence is fine.
        self._say("first", ["one"])
        path = pathlib.Path(server.DATA_DIR) / "chats" / f"{self.chat}.json"
        chat = json.loads(path.read_text())
        chat["messages"].append({"role": "assistant", "content": "   "})
        path.write_text(json.dumps(chat))
        server._agents.clear()
        agent = self._say("second", ["two"])
        self.assertTrue(all(t.strip() for _, t in self._roles_and_text(agent)),
                        f"a blank turn was replayed: {agent.seen_history}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
