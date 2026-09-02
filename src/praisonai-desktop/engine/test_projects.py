"""A project is standing context, not just a sidebar label.

"Move to project" regrouped the sidebar and changed nothing the model saw: a
chat filed under "Alpha" got no Alpha-specific instructions and answered
exactly like a chat filed under nothing. These tests pin the fix -- a
per-project instructions string, prepended to every turn of its chats -- and
guard the parts that must stay untouched: the transcript, the auto-title, and
a chat with no project.

The agent is stubbed. It records the prompt it was handed, because what the
model is shown is the thing under test; it never reaches a provider.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_HOME = tempfile.mkdtemp(prefix="praison-project-test-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ.setdefault("PRAISONAI_KEYCHAIN_SERVICE", "ai.praison.desktop.test")

import server                                            # noqa: E402


class StubAgent:
    """An agent whose stream is fixed, recording the prompt it was given."""

    def __init__(self, chunks=("ok",)):
        self.chunks = list(chunks)
        self.chat_history = []
        self.seen_prompt = None

    def _append_to_chat_history(self, message):
        self.chat_history.append(message)

    def start(self, prompt, stream=True, **kwargs):
        self.seen_prompt = prompt
        for chunk in self.chunks:
            yield chunk


class Projects(unittest.TestCase):
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
        server.save_projects({})

    def _post(self, path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")

    def _get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=30) as r:
            return json.loads(r.read() or b"{}")

    def _chat(self, chat_id, prompt="hello"):
        # /chat is an SSE stream, not JSON -- read and discard the frames.
        agent = StubAgent()
        server._agents[chat_id] = agent
        server._agents[chat_id + "\x00notools"] = agent
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/chat",
            data=json.dumps({"prompt": prompt, "chat_id": chat_id,
                             "session": chat_id}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        return agent

    # -- the reported bug ------------------------------------------------

    def test_only_the_project_chat_carries_the_project_instructions(self):
        # The heart of the issue: two chats, one in a project with standing
        # instructions, one in none. Only the project chat's turn should carry
        # them.
        self._post("/projects", {"project": "Alpha",
                                 "instructions": "Always answer in French."})
        self._post("/project/plain", {"project": ""})
        self._post("/project/inproj", {"project": "Alpha"})

        plain = self._chat("plain")
        inproj = self._chat("inproj")

        self.assertNotIn("French", plain.seen_prompt or "",
                         "a chat in no project inherited project instructions")
        self.assertIn("Always answer in French.", inproj.seen_prompt or "",
                      "a chat in the project did not inherit its instructions")

    def test_the_instructions_lead_the_prompt(self):
        self._post("/projects", {"project": "Alpha",
                                 "instructions": "Answer in French."})
        self._post("/project/c", {"project": "Alpha"})
        agent = self._chat("c", prompt="what is the time")
        self.assertTrue((agent.seen_prompt or "").startswith("Answer in French."),
                        "project instructions must precede the user's turn")
        self.assertIn("what is the time", agent.seen_prompt)

    # -- what must stay untouched ---------------------------------------

    def test_the_transcript_records_only_what_the_user_typed(self):
        # The preamble rides in front of one turn; the stored history must not
        # gain it, or reopening the chat -- and its auto-title -- would show it.
        self._post("/projects", {"project": "Alpha",
                                 "instructions": "Answer in French."})
        self._post("/project/keep", {"project": "Alpha"})
        self._chat("keep", prompt="bonjour question")
        chat = server.load_chat("keep")
        users = [m["content"] for m in chat["messages"] if m["role"] == "user"]
        self.assertEqual(users, ["bonjour question"],
                         f"the project preamble leaked into the transcript: {users}")
        self.assertNotIn("French", chat.get("title", ""))

    def test_a_project_without_instructions_changes_nothing(self):
        self._post("/project/bare", {"project": "Beta"})
        agent = self._chat("bare", prompt="hi there")
        self.assertEqual(agent.seen_prompt, "hi there")

    # -- the endpoint ----------------------------------------------------

    def test_get_projects_reports_stored_instructions(self):
        self._post("/projects", {"project": "Alpha", "instructions": "Be terse."})
        data = self._get("/projects")
        self.assertIn("Alpha", data["projects"])
        self.assertEqual(data["instructions"]["Alpha"], "Be terse.")

    def test_blank_instructions_clear_the_project(self):
        self._post("/projects", {"project": "Alpha", "instructions": "x"})
        self._post("/projects", {"project": "Alpha", "instructions": ""})
        self.assertNotIn("Alpha", server.load_projects())

    def test_a_project_keeps_instructions_without_any_chat(self):
        # Instructions can be authored before the first chat is filed there.
        self._post("/projects", {"project": "Empty", "instructions": "later."})
        self.assertIn("Empty", self._get("/projects")["projects"])

    def test_post_projects_requires_a_name(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/projects",
            data=json.dumps({"instructions": "x"}).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
