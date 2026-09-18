"""Unit tests for knowledge supervisor."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import knowledge


class KnowledgeSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="desktop-knowledge-"))
        self.sup = knowledge.KnowledgeSupervisor(self.home)

    def test_configure_requires_folder(self):
        with self.assertRaises(ValueError):
            self.sup.configure(["/no/such/folder"])

    def test_configure_persists(self):
        d = self.home / "docs"
        d.mkdir()
        st = self.sup.configure([str(d)])
        self.assertEqual(st["paths"], [str(d.resolve())])
        self.assertFalse(st["ready"])

    def test_status_empty(self):
        st = self.sup.status()
        self.assertEqual(st["paths"], [])
        self.assertFalse(st["ready"])

    def test_fallback_scan_finds_small_file(self):
        d = self.home / "docs"
        d.mkdir()
        (d / "e2e-marker.txt").write_text(
            "PraisonAI desktop E2E secret code: NEBULA-7742", encoding="utf-8"
        )
        ctx = self.sup._fallback_scan("What is the secret code?", [str(d)])
        self.assertIn("NEBULA-7742", ctx)


if __name__ == "__main__":
    unittest.main()
