"""The picker must not save a model this build cannot run.

A slashed provider id (ollama/llama3.2, gemini-2.0-flash via a provider prefix)
takes praisonaiagents' custom-LLM path, which needs litellm -- and the lean
desktop venv installs praisonaiagents without its `llm` extra, so litellm is
absent. Left unchecked, the id saved fine and every turn then failed with an
import error or a bare-OpenAI 404, with nothing telling the user the id was
unsupported *in this build*.

These tests assert the EFFECT over a real socket: with litellm unavailable,
POST /settings must answer 4xx with an explanation and leave the model
unchanged; a bare id must still save. The mutation is direct -- remove the guard
in do_POST and the 4xx tests go red.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

_HOME = tempfile.mkdtemp(prefix="praison-model-support-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test." + str(os.getpid())

_spec = importlib.util.spec_from_file_location(
    "engine_server_model_support", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class ModelSupportUnit(unittest.TestCase):
    """The pure predicate, without a socket."""

    def test_a_slashed_id_takes_the_litellm_path(self):
        self.assertTrue(server.model_needs_litellm("ollama/llama3.2"))
        self.assertTrue(server.model_needs_litellm("anthropic/claude-3"))

    def test_a_bare_id_does_not(self):
        self.assertFalse(server.model_needs_litellm("gpt-4o-mini"))
        self.assertFalse(server.model_needs_litellm(""))

    def test_the_reason_matches_the_litellm_capability(self):
        # The message appears exactly when the id needs litellm and it is not
        # available; never for a bare id, and never when litellm is present.
        available = server.litellm_available()
        if available:
            self.assertIsNone(server.unsupported_model_reason("ollama/llama3.2"))
        else:
            self.assertIsNotNone(server.unsupported_model_reason("ollama/llama3.2"))
        self.assertIsNone(server.unsupported_model_reason("gpt-4o-mini"))


class ModelSupportOverTheWire(unittest.TestCase):
    """Drive the real Handler over a real socket."""

    def setUp(self):
        server.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if server.SETTINGS_PATH.exists():
            server.SETTINGS_PATH.unlink()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_a_slashed_id_is_rejected_when_litellm_is_absent(self):
        if server.litellm_available():
            self.skipTest("litellm is installed in this venv; the guard is inert")
        status, body = self.call("POST", "/settings", {"model": "ollama/llama3.2"})
        self.assertGreaterEqual(status, 400)
        self.assertLess(status, 500)
        payload = json.loads(body)
        self.assertFalse(payload.get("ok"))
        self.assertIn("ollama/llama3.2", payload.get("error", ""))

    def test_a_rejected_write_does_not_change_the_model(self):
        if server.litellm_available():
            self.skipTest("litellm is installed in this venv; the guard is inert")
        self.call("POST", "/settings", {"model": "gpt-4o-mini"})
        self.call("POST", "/settings", {"model": "ollama/llama3.2"})
        self.assertEqual(server.load_settings().get("model"), "gpt-4o-mini",
                         "a rejected model write still changed the saved model")

    def test_a_bare_id_still_saves(self):
        status, body = self.call("POST", "/settings", {"model": "gpt-4o"})
        self.assertEqual(status, 200)
        self.assertEqual(server.load_settings().get("model"), "gpt-4o")

    def test_health_reports_the_litellm_capability(self):
        _, body = self.call("GET", "/health")
        payload = json.loads(body)
        self.assertIn("litellm", payload)
        self.assertEqual(payload["litellm"], server.litellm_available())


if __name__ == "__main__":
    unittest.main()
