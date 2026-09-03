"""The three approval modes must mean three different things.

Settings offers `ask` / `smart` ("Ask for risky actions") / `never`, but the
gate only ever tested `never`, so `smart` fell through to the same prompt as
`ask` on every call -- a safety control that silently did nothing. These tests
pin the behaviour that gives `smart` its own meaning: low-risk reads pass
without a card, medium-or-higher tools still raise one.
"""

import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("PRAISONAI_DESKTOP_HOME", tempfile.mkdtemp(prefix="praison-smart-test-"))
os.environ.setdefault("PRAISONAI_KEYCHAIN_SERVICE", "ai.praison.desktop.test")

import server                                            # noqa: E402


def _tool(name):
    for fn in server._builtin_tools():
        if fn.__name__ == name:
            return fn
    raise AssertionError(f"no such builtin tool: {name}")


class SmartApprovalGate(unittest.TestCase):
    def setUp(self):
        self._emitted = []

        # A real user answers the card; here a stub denies it the instant it is
        # raised, so a gate that prompts returns promptly instead of blocking
        # the test for the full approval timeout.
        def _emit(event, payload):
            self._emitted.append((event, payload))
            if event == "approval_request":
                threading.Thread(
                    target=lambda: server.resolve_approval(payload["approval_id"], "deny"),
                    daemon=True,
                ).start()

        server._set_emitter(_emit)
        self.addCleanup(lambda: server._set_emitter(None))

    def _requests(self):
        return [p for e, p in self._emitted if e == "approval_request"]

    def test_smart_passes_low_risk_read_without_a_card(self):
        server.save_settings({"approval_mode": "smart"})
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("hello")
            path = f.name
        self.addCleanup(lambda: os.unlink(path))
        out = _tool("read_file")(path)
        self.assertEqual(out, "hello")
        self.assertEqual(self._requests(), [])

    def test_smart_still_prompts_for_fetch_url(self):
        server.save_settings({"approval_mode": "smart"})
        # No decision arrives, so the gate declines -- but it must have asked.
        out = _tool("fetch_url")("https://example.com")
        self.assertEqual(out, "The user declined this tool call.")
        self.assertEqual(len(self._requests()), 1)
        self.assertEqual(self._requests()[0]["name"], "fetch_url")

    def test_ask_still_prompts_for_low_risk_read(self):
        server.save_settings({"approval_mode": "ask"})
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("hello")
            path = f.name
        self.addCleanup(lambda: os.unlink(path))
        out = _tool("read_file")(path)
        self.assertEqual(out, "The user declined this tool call.")
        self.assertEqual(len(self._requests()), 1)

    def test_never_passes_everything(self):
        server.save_settings({"approval_mode": "never"})
        out = _tool("fetch_url")("not-a-url")
        self.assertEqual(out, "Only http and https URLs are supported.")
        self.assertEqual(self._requests(), [])


if __name__ == "__main__":
    unittest.main()
