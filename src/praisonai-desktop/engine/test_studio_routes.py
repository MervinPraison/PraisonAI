"""HTTP integration tests for /studio/* (regression for do_GET urlparse shadowing)."""

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
ORIGIN = "http://tauri.localhost"


class EngineProcess:
    def __init__(self):
        self.home = tempfile.mkdtemp(prefix="praison-studio-routes-")
        env = dict(os.environ, PRAISONAI_DESKTOP_HOME=self.home)
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
                raise RuntimeError("engine exited before announcing a port")
            if PORT_MARKER in line:
                return int(line.split(PORT_MARKER, 1)[1].strip())
        raise RuntimeError(f"no port within {timeout}s")

    def request(self, path, payload=None, method=None, timeout=30):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        req = urllib.request.Request(
            self.url(path),
            data=data,
            method=method or ("POST" if data is not None else "GET"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return err.code, {}

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def shutdown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class StudioRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = EngineProcess()

    @classmethod
    def tearDownClass(cls):
        cls.engine.shutdown()

    def test_health_returns_ok(self):
        req = urllib.request.Request(self.engine.url("/health"))
        with urllib.request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read())
        self.assertTrue(body.get("ok"))

    def test_studio_models_includes_flare_default(self):
        status, body = self.engine.request("/studio/models")
        self.assertEqual(status, 200)
        ids = [m["id"] for m in body.get("image", [])]
        self.assertIn("openai/gpt-image-2.5-flare-2026-09-08", ids)
        defs = body.get("image_defaults") or {}
        self.assertEqual(defs.get("quality"), "low")
        self.assertEqual(defs.get("size"), "1024x1024")

    def test_create_project_and_list(self):
        status, body = self.engine.request(
            "/studio/projects", {"name": "Auto test"}, method="POST"
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        pid = body["project"]["id"]
        status, listed = self.engine.request("/studio/projects")
        self.assertEqual(status, 200)
        ids = [p["id"] for p in listed.get("projects", [])]
        self.assertIn(pid, ids)

    def test_generate_image_job_lifecycle_without_api_key(self):
        _, created = self.engine.request(
            "/studio/projects", {"name": "Gen test"}, method="POST"
        )
        pid = created["project"]["id"]
        status, body = self.engine.request(
            f"/studio/projects/{pid}/generate",
            {
                "kind": "image",
                "model": "openai/gpt-image-2.5-flare-2026-09-08",
                "prompt": "automated test ping",
                "image_quality": "low",
                "image_size": "1024x1024",
                "n_variants": 1,
            },
            method="POST",
        )
        self.assertEqual(status, 200)
        jobs = body.get("jobs") or []
        self.assertEqual(len(jobs), 1)
        jid = jobs[0]["id"]
        deadline = time.time() + 45
        final = None
        while time.time() < deadline:
            _, polled = self.engine.request(f"/studio/jobs/{jid}")
            final = polled.get("job") or {}
            if final.get("status") in ("completed", "failed"):
                break
            time.sleep(0.5)
        self.assertIsNotNone(final)
        self.assertIn(final.get("status"), ("completed", "failed"))
        if final.get("status") == "failed":
            self.assertTrue(final.get("error"))


if __name__ == "__main__":
    unittest.main()
