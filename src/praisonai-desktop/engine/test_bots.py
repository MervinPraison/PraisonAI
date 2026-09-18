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

    def test_add_discord_channel(self):
        ch = self.sup.add_channel({"platform": "discord", "name": "Discord"})
        self.assertEqual(ch["platform"], "discord")
        self.assertEqual(ch["token_ref"], "env:DISCORD_BOT_TOKEN")

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
        self.assertIn("test-token-1234567890", text)

    def test_patch_gateway_unknown_user_policies(self):
        self.sup.add_channel({"platform": "slack", "name": "Slack"})
        self.sup.add_channel({"platform": "telegram", "name": "TG"})
        migrated = (
            "channels:\n"
            "  slack:\n"
            "    token: xoxb-test\n"
            "    app_token: xapp-test\n"
            "  telegram:\n"
            "    token: 123:abc\n"
            "    unknown_user_policy: allow\n"
        )
        self.sup.gateway_config.write_text(migrated, encoding="utf-8")
        self.sup._patch_gateway_unknown_user_policies()
        text = self.sup.gateway_config.read_text(encoding="utf-8")
        self.assertIn("  slack:\n    token: xoxb-test\n    app_token: xapp-test\n    unknown_user_policy: allow", text)

    def test_gateway_yaml_generated(self):
        from unittest.mock import patch

        os.environ["TELEGRAM_BOT_TOKEN"] = "1234567890:" + "x" * 30
        self.sup.add_channel({"platform": "telegram"})
        with patch.object(bots, "load_dotenv_file"):
            self.sup._write_gateway_yaml(8765)
        text = self.sup.gateway_config.read_text(encoding="utf-8")
        self.assertIn("gateway:", text)
        self.assertIn("telegram:", text)
        self.assertIn("8765", text)
        self.assertNotIn("${TELEGRAM_BOT_TOKEN}", text)
        self.assertIn("1234567890:", text)

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

    def test_load_dotenv_replaces_empty_inherited_var(self):
        env_path = __import__("pathlib").Path(self.home) / ".praisonai.env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("TELEGRAM_BOT_TOKEN=1234567890:ABCDEF\n", encoding="utf-8")
        os.environ["TELEGRAM_BOT_TOKEN"] = ""
        bots.load_dotenv_file(env_path)
        self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "1234567890:ABCDEF")
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

    def test_load_dotenv_overrides_stale_token_from_praison_env(self):
        import pathlib
        from unittest.mock import patch

        env_path = pathlib.Path(self.home) / ".praisonai" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("TELEGRAM_BOT_TOKEN=new-from-file\n", encoding="utf-8")
        os.environ["TELEGRAM_BOT_TOKEN"] = "stale-from-shell"
        with patch.object(pathlib.Path, "home", return_value=pathlib.Path(self.home)):
            bots.load_dotenv_file(env_path)
        self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "new-from-file")
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
