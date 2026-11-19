"""A page that re-points its own hostname at 127.0.0.1 must not reach the engine.

test_origin_gate.py covers pages on another origin: the browser sends Origin and
the engine refuses it. A page on foreign.example can instead make its own name
resolve to 127.0.0.1 (DNS rebinding). Its requests are then same-origin to the
page, and a same-origin GET carries no Origin header at all, so the origin gate
lets it through and the page can read the reply: every chat transcript, the
project instructions, the MCP server list, the logs.

The Host header still names foreign.example, and a page cannot change it. So the
engine also refuses a Host that is not one of its own loopback names.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import ast
import importlib.util
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

_HOME = tempfile.mkdtemp(prefix="praison-host-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test.host." + str(os.getpid())

_SERVER_PY = pathlib.Path(__file__).with_name("server.py")
_spec = importlib.util.spec_from_file_location("engine_server_host", _SERVER_PY)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

assert server.KEYCHAIN_SERVICE != "ai.praison.desktop", (
    "refusing to run: this test would write into the real keychain service")


class HostGateOverHttp(unittest.TestCase):
    """Drive the real Handler over a real socket."""

    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.server_address[1]
        self.base = "http://127.0.0.1:%d" % self.port

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, method, path, host=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        data = b"{}" if method == "POST" else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_a_rebound_page_cannot_read_transcripts(self):
        """Same-origin GET from foreign.example: no Origin, foreign Host."""
        for path in ("/chats", "/settings", "/projects", "/mcp", "/logs"):
            status = self.call("GET", path, host="foreign.example:%d" % self.port)
            self.assertEqual(status, 403, path)

    def test_a_rebound_page_cannot_write(self):
        status = self.call("POST", "/settings", host="foreign.example:%d" % self.port)
        self.assertEqual(status, 403)

    def test_a_lookalike_host_is_refused(self):
        for host in ("127.0.0.1.foreign.example:%d" % self.port,
                     "localhost.foreign.example:%d" % self.port,
                     "foreign.example"):
            self.assertEqual(self.call("GET", "/chats", host=host), 403, host)

    def test_loopback_names_still_work(self):
        """The webview, cli.py and curl address the engine by loopback name."""
        for host in ("127.0.0.1:%d" % self.port, "localhost:%d" % self.port,
                     "LOCALHOST:%d" % self.port, "[::1]:%d" % self.port):
            self.assertEqual(self.call("GET", "/chats", host=host), 200, host)

    def test_the_app_still_works(self):
        self.assertEqual(self.call("GET", "/chats", origin="tauri://localhost"), 200)
        self.assertEqual(self.call("GET", "/health"), 200)


class EveryMethodIsGated(unittest.TestCase):
    """Every do_* handler must start with the request gate, so a new HTTP
    method cannot skip the Origin and Host checks."""

    def test_every_do_method_calls_the_gate_first(self):
        tree = ast.parse(_SERVER_PY.read_text(encoding="utf-8"))
        handler = next(n for n in tree.body
                       if isinstance(n, ast.ClassDef) and n.name == "Handler")
        methods = [f for f in handler.body
                   if isinstance(f, ast.FunctionDef) and f.name.startswith("do_")]
        self.assertGreaterEqual(len(methods), 5)
        for fn in methods:
            first = fn.body[0]
            src = ast.unparse(first)
            self.assertIn("self._origin_ok()", src,
                          f"{fn.name} does not check the request gate first")


if __name__ == "__main__":
    unittest.main()
