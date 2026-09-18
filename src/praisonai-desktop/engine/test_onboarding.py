"""Onboarding API payload tests."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

_HOME = tempfile.mkdtemp(prefix="desktop-onboard-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME

_spec = importlib.util.spec_from_file_location(
    "engine_server_onboard", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class OnboardingPayloadTests(unittest.TestCase):
    def test_payload_shape(self):
        p = server.onboarding_payload()
        self.assertIn("complete", p)
        self.assertIn("api_key_set", p)
        self.assertIn("knowledge_ready", p)
        self.assertIn("channels_count", p)
        self.assertEqual(p["env_hints"]["discord"], "DISCORD_BOT_TOKEN")
        self.assertIn("discord", p["channel_platforms"])


if __name__ == "__main__":
    unittest.main()
