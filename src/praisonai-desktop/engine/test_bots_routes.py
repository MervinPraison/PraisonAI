"""HTTP route tests for /bots/* endpoints."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
PORT_MARKER = "PRAISONAI_PORT="


class EngineProcess:
    def __init__(self):
        self.home = tempfile.mkdtemp(prefix="desktop-bots-routes-")
        env = dict(os.environ, PRAISONAI_DESKTOP_HOME=self.home)
        os.environ["TELEGRAM_BOT_TOKEN"] = "1234567890:" + "A" * 30
        self.proc = subprocess.Popen(
            [sys.executable, "-u", ENGINE],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.port = self._await_port()

    def _await_port(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("engine exited early")
            if PORT_MARKER in line:
                return int(line.split(PORT_MARKER, 1)[1].strip())
        raise RuntimeError("no port")

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def request(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url(path),
            data=data,
            method=method or ("POST" if data else "GET"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, {"error": body}

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class BotsRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = EngineProcess()

    def tearDown(self):
        self.engine.close()

    def test_list_channels_empty(self):
        code, body = self.engine.request("/bots/channels")
        self.assertEqual(code, 200)
        self.assertEqual(body["channels"], [])

    def test_add_channel(self):
        code, body = self.engine.request(
            "/bots/channels",
            {
                "platform": "telegram",
                "name": "Test Bot",
                "token_ref": "env:TELEGRAM_BOT_TOKEN",
            },
        )
        self.assertEqual(code, 201)
        self.assertTrue(body["ok"])
        self.assertEqual(body["channel"]["platform"], "telegram")

    def test_gateway_status(self):
        code, body = self.engine.request("/bots/gateway")
        self.assertEqual(code, 200)
        self.assertIn("state", body)

    def test_add_discord_channel(self):
        os.environ["DISCORD_BOT_TOKEN"] = "MT" + "x" * 20 + ".Y" + "z" * 30
        code, body = self.engine.request(
            "/bots/channels",
            {
                "platform": "discord",
                "name": "Discord Test",
                "token_ref": "env:DISCORD_BOT_TOKEN",
                "unknown_user_policy": "allow",
            },
        )
        self.assertIn(code, (200, 201))
        self.assertTrue(body.get("ok", True))
        ch = body.get("channel") or body
        self.assertEqual(ch.get("platform"), "discord")


if __name__ == "__main__":
    unittest.main()
