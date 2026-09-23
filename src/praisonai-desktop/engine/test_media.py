"""Tests for media supervisor (no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import media


class MediaSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="desktop-media-"))
        self.sup = media.MediaSupervisor(self.home)

    def test_capabilities(self):
        caps = self.sup.capabilities()
        self.assertTrue(caps["image"])
        self.assertIn("dall-e-3", caps["image_models"])
        self.assertIn("video_models", caps)

    def test_video_models_include_multiple_providers(self):
        models = self.sup.list_video_models()
        providers = {m["provider"] for m in models}
        self.assertIn("replicate", providers)
        self.assertIn("openai", providers)
        self.assertIn("gemini", providers)
        for m in models:
            self.assertIn("id", m)
            self.assertIn("display_name", m)
            self.assertIn("configured", m)

    def test_video_models_configured_reflects_env(self):
        import os

        saved = {
            k: os.environ.pop(k, None)
            for k in ("REPLICATE_API_TOKEN", "REPLICATE_API_KEY")
        }
        try:
            os.environ["REPLICATE_API_TOKEN"] = "r8_test"
            by_id = {m["id"]: m for m in self.sup.list_video_models()}
            self.assertTrue(by_id["replicate/minimax/video-01"]["configured"])
        finally:
            os.environ.pop("REPLICATE_API_TOKEN", None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_minimax_is_preset_not_sole_path(self):
        ids = [m["id"] for m in self.sup.list_video_models()]
        self.assertIn("replicate/minimax/video-01", ids)
        self.assertGreater(len(ids), 1)

    def test_generate_video_rejects_unknown_model(self):
        with self.assertRaises(ValueError):
            self.sup.generate_video("a cat", settings={}, model="replicate/bogus/model")

    def test_generate_video_rejects_arbitrary_replicate_id(self):
        with self.assertRaises(ValueError):
            self.sup.generate_video(
                "a cat", settings={}, model="replicate/minimax/video-99"
            )

    def test_generate_video_sdk_success_returns_data_url(self):
        import sys
        import types

        payload = b"\x00\x00fake-mp4"

        class _FakeAgent:
            def __init__(self, *a, **k):
                pass

            def start(self, prompt, wait=True, output=None, **k):
                Path(output).write_bytes(payload)
                return payload

        fake_mod = types.ModuleType("praisonaiagents")
        fake_mod.VideoAgent = _FakeAgent
        saved = sys.modules.get("praisonaiagents")
        sys.modules["praisonaiagents"] = fake_mod
        try:
            res = self.sup.generate_video(
                "a cat", settings={}, model="openai/sora-2"
            )
        finally:
            if saved is not None:
                sys.modules["praisonaiagents"] = saved
            else:
                sys.modules.pop("praisonaiagents", None)

        self.assertIsNone(res["url"])
        self.assertTrue(res["data_url"].startswith("data:video/mp4;base64,"))
        self.assertTrue(Path(res["path"]).is_file())

    def test_generate_video_sdk_failure_raises(self):
        import sys
        import types

        class _Status:
            status = "failed"

        class _FakeAgent:
            def __init__(self, *a, **k):
                pass

            def start(self, prompt, wait=True, output=None, **k):
                return _Status()

        fake_mod = types.ModuleType("praisonaiagents")
        fake_mod.VideoAgent = _FakeAgent
        saved = sys.modules.get("praisonaiagents")
        sys.modules["praisonaiagents"] = fake_mod
        try:
            with self.assertRaises(RuntimeError):
                self.sup.generate_video(
                    "a cat", settings={}, model="openai/sora-2"
                )
        finally:
            if saved is not None:
                sys.modules["praisonaiagents"] = saved
            else:
                sys.modules.pop("praisonaiagents", None)

    def test_generate_image_requires_key(self):
        import os

        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(ValueError):
                self.sup.generate_image("a cat", settings={})
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
