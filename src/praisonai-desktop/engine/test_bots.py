"""Unit tests for desktop bot/channel supervisor."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

import bots


class BotSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="desktop-bots-")
        self.sup = bots.BotSupervisor(
            __import__("pathlib").Path(self.home),
            sys.executable,
        )

    def test_add_telegram_channel(self):
        ch = self.sup.add_channel(
            {"platform": "telegram", "name": "TG", "token_ref": "env:TELEGRAM_BOT_TOKEN"}
        )
        self.assertEqual(ch["platform"], "telegram")
        self.assertTrue(ch["id"])

    def test_add_slack_requires_app_token_field(self):
        ch = self.sup.add_channel({"platform": "slack", "name": "Slack"})
        self.assertIn("app_token_ref", ch)

    def test_write_bot_yaml_uses_env_placeholder(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token-1234567890"
        ch = self.sup.add_channel(
            {"platform": "telegram", "token_ref": "env:TELEGRAM_BOT_TOKEN"}
        )
        path = self.sup._write_bot_yaml(ch)
        text = path.read_text(encoding="utf-8")
        self.assertIn("unknown_user_policy: allow", text)
        self.assertIn("${TELEGRAM_BOT_TOKEN}", text)

    def test_gateway_yaml_generated(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "x" * 20
        self.sup.add_channel({"platform": "telegram"})
        self.sup._write_gateway_yaml(8765)
        text = self.sup.gateway_config.read_text(encoding="utf-8")
        self.assertIn("gateway:", text)
        self.assertIn("telegram:", text)
        self.assertIn("8765", text)

    def test_persist_channels(self):
        self.sup.add_channel({"platform": "telegram", "name": "A"})
        path = self.sup.channels_path
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)

    def test_delete_channel_does_not_deadlock(self):
        ch = self.sup.add_channel({"platform": "telegram", "name": "A"})
        self.assertTrue(self.sup.delete_channel(ch["id"]))
        self.assertEqual(self.sup.list_channels(), [])


if __name__ == "__main__":
    unittest.main()
