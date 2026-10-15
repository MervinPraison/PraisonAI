"""Tests for check_extension_loaded target matching (#5785)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("aiohttp")

from praisonai_browser.diagnostics import DiagnosticStatus, check_extension_loaded


class _CM:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *exc):
        return False


def _status(targets):
    resp = MagicMock(status=200)

    async def _json():
        return targets

    resp.json = _json
    session = MagicMock()
    session.get = lambda *a, **k: _CM(resp)
    with patch("aiohttp.ClientSession", lambda: _CM(session)):
        return asyncio.run(check_extension_loaded()).status


@pytest.mark.parametrize("target", [
    {"type": "service_worker", "url": "chrome-extension://egjhiolafabdaakjboedhcappifmhcfk/sw.js"},
    {"type": "background_page", "url": "chrome-extension://randomid/bg.html", "title": "Browser Agent"},
])
def test_detects_extension_targets(target):
    assert _status([target]) == DiagnosticStatus.PASS


@pytest.mark.parametrize("target", [
    {"type": "service_worker", "url": "https://example.com/browser-agent/sw.js"},
    {"type": "page", "url": "https://github.com/praisonai", "title": "Browser Agent"},
    {"type": "service_worker", "url": "chrome-extension://otherid/sw.js", "title": "Other"},
])
def test_ignores_unrelated_targets(target):
    assert _status([target]) == DiagnosticStatus.FAIL
