"""Tests for Creative Studio persistence and timeline export."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import studio  # noqa: E402


class BuildImageKwargsTests(unittest.TestCase):
    def test_flare_low_cost_defaults(self):
        kw = studio.build_image_kwargs("openai/gpt-image-2.5-flare-2026-09-08")
        self.assertEqual(kw["quality"], "low")
        self.assertEqual(kw["size"], "1024x1024")
        self.assertEqual(kw["n"], 1)


class StudioProjectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mgr = studio.StudioManager(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_and_list_projects(self):
        p = self.mgr.create_project("Demo")
        listed = self.mgr.list_projects()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], p["id"])
        self.assertEqual(listed[0]["name"], "Demo")

    def test_add_image_asset(self):
        p = self.mgr.create_project("Refs")
        import base64

        png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        asset = self.mgr.add_image_asset(p["id"], "x.png", png)
        self.assertEqual(asset["type"], "image")
        full = self.mgr.get_project(p["id"])
        self.assertEqual(len(full["assets"]), 1)

    def test_concurrent_asset_appends_do_not_clobber(self):
        import base64
        import threading

        p = self.mgr.create_project("Race")
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()

        def _add(i):
            self.mgr.add_image_asset(p["id"], f"img{i}.png", png)

        threads = [threading.Thread(target=_add, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        full = self.mgr.get_project(p["id"])
        self.assertEqual(len(full["assets"]), 8)

    def test_timeline_and_single_clip_export(self):
        p = self.mgr.create_project("Export")
        proj_path = self.mgr.root / p["id"] / "project.json"
        data = json.loads(proj_path.read_text(encoding="utf-8"))
        rel = "outputs/fake.mp4"
        out = self.mgr.root / p["id"] / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-mp4")
        aid = "asset_test123"
        data["assets"] = [
            {"id": aid, "type": "video", "path": rel, "prompt": "test"}
        ]
        data["timeline"] = [aid]
        proj_path.write_text(json.dumps(data), encoding="utf-8")
        result = self.mgr.export_timeline(p["id"], "out.mp4")
        self.assertTrue(Path(result["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
