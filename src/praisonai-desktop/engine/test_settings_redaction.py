"""No settings reply may carry the API key in cleartext.

GET /settings masked the key from the start. POST /settings answered with
save_settings()'s dict, which begins at load_settings() and so holds the real
secret read back out of the keychain -- meaning every settings write replied
with the credential, including a write that only changed the theme. Combined
with `Access-Control-Allow-Origin: *`, any page the user had open could read
it.

These tests assert the EFFECT: the secret must not appear in the bytes that
leave the process. Asserting the shape of the dict would not have caught it --
the dict was correct, it was simply the wrong dict.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

# Both isolations must be set BEFORE server.py is imported: KEYCHAIN_SERVICE and
# SETTINGS_PATH are bound at module scope. PRAISONAI_DESKTOP_HOME alone moves the
# data directory but NOT the system keyring, which is shared per user -- writing a
# test key under the default service overwrites the real one the person is using,
# and the keychain keeps no previous value to put back. This is not hypothetical:
# it happened while this very test was being written.
_HOME = tempfile.mkdtemp(prefix="praison-redaction-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test." + str(os.getpid())

_spec = importlib.util.spec_from_file_location(
    "engine_server_redaction", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

assert server.KEYCHAIN_SERVICE != "ai.praison.desktop", (
    "refusing to run: this test would write into the real keychain service")

CANARY = "sk-ant-CANARY-do-not-leak-0123456789"


class SettingsRedaction(unittest.TestCase):
    """Drive the real Handler over a real socket; inspect the raw bytes."""

    def setUp(self):
        server.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if server.SETTINGS_PATH.exists():
            server.SETTINGS_PATH.unlink()
        for key in server.SECRET_KEYS:
            server.keychain_set(key, "")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for key in server.SECRET_KEYS:
            server.keychain_set(key, "")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode()

    def test_storing_the_key_does_not_echo_it(self):
        body = self.call("POST", "/settings", {"api_key": CANARY})
        self.assertNotIn(CANARY, body,
                         "POST /settings echoed the API key back in cleartext")

    def test_unrelated_write_does_not_return_the_key(self):
        """The theme write is the damning one: it never mentions the key."""
        self.call("POST", "/settings", {"api_key": CANARY})
        body = self.call("POST", "/settings", {"theme": "dark"})
        self.assertNotIn(CANARY, body,
                         "a theme-only write replied with the stored API key")

    def test_get_does_not_return_the_key(self):
        self.call("POST", "/settings", {"api_key": CANARY})
        self.assertNotIn(CANARY, self.call("GET", "/settings"))

    def test_the_key_is_still_stored_and_usable(self):
        """Redaction must change only what leaves, never what is kept."""
        self.call("POST", "/settings", {"api_key": CANARY})
        self.assertEqual(server.load_settings().get("api_key"), CANARY,
                         "redaction destroyed the stored credential")

    def test_masking_is_not_mistaken_for_a_value(self):
        """An empty key must stay empty, not become eight bullets."""
        self.assertEqual(server.redacted({"api_key": ""})["api_key"], "")

    def test_non_secret_fields_survive(self):
        out = server.redacted({"theme": "dark", "api_key": CANARY})
        self.assertEqual(out["theme"], "dark")
        self.assertNotIn(CANARY, json.dumps(out))

    def test_every_declared_secret_is_covered(self):
        """New entries in SECRET_KEYS must be redacted without new code."""
        probe = {k: "SECRET-" + k for k in server.SECRET_KEYS}
        blob = json.dumps(server.redacted(probe))
        for k in server.SECRET_KEYS:
            self.assertNotIn("SECRET-" + k, blob,
                             "%s is declared secret but is not redacted" % k)


if __name__ == "__main__":
    unittest.main()
