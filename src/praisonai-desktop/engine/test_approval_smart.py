"""approval_mode "smart" must differ from "ask" -- and only where it is safe.

The Settings select offered ask / smart ("Ask for risky actions") / never, and
_gate() checked only for "never". "smart" fell through to the same prompt as
"ask" on every gated call: a safety setting accepted and ignored.

These tests pin the contract by driving _gate() through the real tool
functions, with the approval stream stubbed so a prompt is observable and a
"decision" can be scripted.
"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

os.environ.setdefault("PRAISONAI_DESKTOP_HOME", tempfile.mkdtemp(prefix="praison-smart-"))
os.environ.setdefault("PRAISONAI_KEYCHAIN_SERVICE", "ai.praison.desktop.test.smart")
_spec = importlib.util.spec_from_file_location(
    "engine_server_smart", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class SmartApproval(unittest.TestCase):

    def setUp(self):
        self.prompts = []
        self._settings = {"approval_mode": "smart"}
        self._orig = (server.load_settings, server._emit_now, server._await_decision)
        server.load_settings = lambda: dict(server.DEFAULT_SETTINGS, **self._settings)
        server._emit_now = lambda kind, payload: self.prompts.append((kind, payload))
        server._await_decision = lambda aid: "deny"       # any prompt is refused
        server._tool_events.emit = lambda *a, **k: None   # "a stream exists"
        server._always_allow.clear()
        self.tools = {t.__name__: t for t in server._builtin_tools()}

    def tearDown(self):
        server.load_settings, server._emit_now, server._await_decision = self._orig
        if hasattr(server._tool_events, "emit"):
            del server._tool_events.emit

    def asked(self, name):
        return any(k == "approval_request" and p["name"] == name for k, p in self.prompts)

    def test_smart_lets_a_local_read_through_without_asking(self):
        out = self.tools["list_directory"](".")
        self.assertFalse(self.asked("list_directory"), "smart prompted for a local read")
        self.assertNotIn("declined", out.lower())

    def test_smart_still_asks_before_a_network_fetch(self):
        self.tools["fetch_url"]("http://127.0.0.1:9/never")
        self.assertTrue(self.asked("fetch_url"),
                        "smart let a model-chosen URL go out without asking")

    def test_ask_still_asks_for_everything_gated(self):
        """The fix must not loosen 'ask'."""
        self._settings["approval_mode"] = "ask"
        self.tools["list_directory"](".")
        self.assertTrue(self.asked("list_directory"))

    def test_never_asks_for_nothing(self):
        self._settings["approval_mode"] = "never"
        self.tools["fetch_url"]("http://127.0.0.1:9/never")
        self.assertFalse(self.asked("fetch_url"))

    def test_fetch_url_is_not_low_risk(self):
        """Pin the classification itself, so a future edit has to mean it."""
        self.assertNotIn("fetch_url", server._LOW_RISK_TOOLS)
        self.assertIn("read_file", server._LOW_RISK_TOOLS)

    def test_every_registry_copy_describes_smart_the_same_way(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        texts = [(root / f).read_text(encoding="utf-8") for f in
                 ("ui/index.html", "ui/settings-registry.js", "frontend/src/settings-registry.js")]
        for t in texts:
            self.assertIn('value: "smart", label: "Ask only for network fetches"', t)
            self.assertNotIn("Ask for risky actions", t, "stale label survived in a copy")


if __name__ == "__main__":
    unittest.main()
