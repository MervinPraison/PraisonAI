"""D-13: the sdist does not ship the test suite (it cannot run without the repo's conftest)."""

import os

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_manifest_prunes_tests():
    with open(os.path.join(PKG_ROOT, "MANIFEST.in"), encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    assert "prune tests" in lines
