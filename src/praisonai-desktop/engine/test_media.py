"""Tests for media supervisor (no network)."""

from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class MiniMaxImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="desktop-minimax-image-")
        self.addCleanup(self.tmp.cleanup)
        self.sup = media.MediaSupervisor(Path(self.tmp.name))
        self.env = patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_catalog_contains_image_model(self):
        self.assertIn(media.MINIMAX_IMAGE_MODEL, self.sup.capabilities()["image_models"])

    def test_regional_requests_save_images_and_map_dimensions(self):
        image = b"generated-image"
        for region, endpoint in media.MINIMAX_IMAGE_ENDPOINTS.items():
            with self.subTest(region=region), patch.dict(os.environ, {"MINIMAX_IMAGE_REGION": region}):
                payload = {
                    "base_resp": {"status_code": 0},
                    "data": {"image_urls": ["https://example.com/generated.png"]},
                }
                with patch("media.urllib.request.urlopen", side_effect=[
                    io.BytesIO(json.dumps(payload).encode()), io.BytesIO(image),
                ]) as request:
                    result = self.sup.generate_image(
                        "a lighthouse", settings={"api_key": "unrelated-key"},
                        model=media.MINIMAX_IMAGE_MODEL, size="1792x1024",
                    )
                req = request.call_args_list[0].args[0]
                self.assertEqual(req.full_url, endpoint)
                self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
                self.assertEqual(json.loads(req.data), {
                    "model": media.MINIMAX_IMAGE_MODEL.split("/", 1)[1],
                    "prompt": "a lighthouse", "width": 1792, "height": 1024,
                    "n": 1, "response_format": "url",
                })
                self.assertEqual(Path(result["path"]).read_bytes(), image)
                self.assertEqual(result["url"], "https://example.com/generated.png")
                self.assertEqual(result["model"], media.MINIMAX_IMAGE_MODEL)
                self.assertEqual(result["data_url"], "data:image/png;base64," + base64.b64encode(image).decode())

    def test_base64_response_is_saved_without_download(self):
        image = b"generated-image"
        payload = {
            "base_resp": {"status_code": 0},
            "data": {"image_base64": [base64.b64encode(image).decode()]},
        }
        with patch("media.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result = self.sup.generate_image("a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL)
        request.assert_called_once()
        self.assertEqual(Path(result["path"]).read_bytes(), image)
        self.assertIsNone(result["url"])

    def test_application_error_and_empty_output_fail_without_saving(self):
        for payload, message in [
            ({"base_resp": {"status_code": 1004, "status_msg": "Authentication failed"}}, "Authentication failed"),
            ({"base_resp": {"status_code": 0}, "data": {"image_urls": []}}, "returned no images"),
            ({"data": {}}, "generation failed"),
        ]:
            with self.subTest(payload=payload), patch("media.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as request:
                with self.assertRaisesRegex(RuntimeError, message):
                    self.sup.generate_image("a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL)
                request.assert_called_once()
        self.assertEqual(list((self.sup.out / "images").iterdir()), [])

    def test_malformed_payload_shapes_fail_without_saving(self):
        for payload in ["error", [1, 2, 3], {"base_resp": "error"}, {"base_resp": [1]},
                        {"base_resp": {"status_code": 0}, "data": [1]}]:
            with self.subTest(payload=payload), patch(
                "media.urllib.request.urlopen",
                return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                with self.assertRaises(RuntimeError):
                    self.sup.generate_image(
                        "a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL
                    )
        self.assertEqual(list((self.sup.out / "images").iterdir()), [])

    def test_empty_download_fails_without_saving(self):
        payload = {
            "base_resp": {"status_code": 0},
            "data": {"image_urls": ["https://example.com/generated.png"]},
        }
        with patch("media.urllib.request.urlopen", side_effect=[
            io.BytesIO(json.dumps(payload).encode()), io.BytesIO(b""),
        ]):
            with self.assertRaisesRegex(RuntimeError, "empty"):
                self.sup.generate_image(
                    "a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL
                )
        self.assertEqual(list((self.sup.out / "images").iterdir()), [])

    def test_key_loaded_from_praison_env_when_absent(self):
        import pathlib

        home = pathlib.Path(self.tmp.name)
        env_dir = home / ".praisonai"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / ".env").write_text("MINIMAX_API_KEY=from-dotenv\n", encoding="utf-8")
        image = b"generated-image"
        payload = {
            "base_resp": {"status_code": 0},
            "data": {"image_base64": [base64.b64encode(image).decode()]},
        }
        with patch.dict(os.environ, {}, clear=True), \
                patch("pathlib.Path.home", return_value=home), \
                patch("media.urllib.request.urlopen",
                      return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result = self.sup.generate_image(
                "a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL
            )
        req = request.call_args_list[0].args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer from-dotenv")
        self.assertEqual(pathlib.Path(result["path"]).read_bytes(), image)

    def test_requires_dedicated_key(self):
        with patch.dict(os.environ, {}, clear=True), patch("media.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "MINIMAX_API_KEY"):
                self.sup.generate_image("a lighthouse", settings={"api_key": "unrelated-key"}, model=media.MINIMAX_IMAGE_MODEL)
            request.assert_not_called()

    def test_unknown_region_is_rejected_before_request(self):
        with patch.dict(os.environ, {"MINIMAX_IMAGE_REGION": "unknown"}), patch("media.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "MINIMAX_IMAGE_REGION"):
                self.sup.generate_image("a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL)
            request.assert_not_called()

    def test_invalid_sizes_and_models_are_rejected_before_request(self):
        with patch("media.urllib.request.urlopen") as request:
            for size in ("auto", "1x1024", "1025x1024", "4096x1024", "1024x1024x1024"):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    self.sup.generate_image("a lighthouse", settings={}, model=media.MINIMAX_IMAGE_MODEL, size=size)
            with self.assertRaisesRegex(ValueError, "Unknown MiniMax image model"):
                self.sup.generate_image("a lighthouse", settings={}, model="minimax/unknown")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
