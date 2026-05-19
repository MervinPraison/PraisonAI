"""Regression tests for SSRF hardening in spider_tools._validate_url.

Covers GHSA-q9pw-vmhh-384g: a URL such as ``http://127.0.0.1:6666\\@1.1.1.1``
parses with hostname ``1.1.1.1`` via :func:`urllib.parse.urlparse` but is
dispatched to ``127.0.0.1`` by ``requests``. The validator must reject any
URL whose authority disagrees with the actual destination so that hostname
allow/deny checks cannot be smuggled past.
"""

from praisonaiagents.tools.spider_tools import SpiderTools


def test_rejects_backslash_smuggle_in_authority():
    spider = SpiderTools()
    # Real-world bypass payload from the advisory.
    assert spider._validate_url("http://127.0.0.1:6666\\@1.1.1.1") is False


def test_rejects_backslash_anywhere_in_url():
    spider = SpiderTools()
    assert spider._validate_url("http://example.com\\foo") is False


def test_rejects_control_characters():
    spider = SpiderTools()
    assert spider._validate_url("http://example.com\x00.evil.com") is False
    assert spider._validate_url("http://example.com\r\n.evil.com") is False


def test_allows_normal_public_url():
    spider = SpiderTools()
    assert spider._validate_url("https://example.com/path?q=1") is True


def test_still_blocks_loopback():
    spider = SpiderTools()
    assert spider._validate_url("http://127.0.0.1:6666/") is False
    assert spider._validate_url("http://localhost/") is False


def test_blocks_alternate_loopback_encodings():
    """GHSA-5c6w-wwfq-7qqm: non-canonical loopback host forms."""
    spider = SpiderTools()
    assert spider._validate_url("http://localhost.:8765/") is False
    assert spider._validate_url("http://127.1:8765/") is False
    assert spider._validate_url("http://0177.0.0.1:8765/") is False
    assert spider._validate_url("http://0x7f000001:8765/") is False
    assert spider._validate_url("http://2130706433:8765/") is False


def test_rejects_non_string_input():
    spider = SpiderTools()
    assert spider._validate_url(None) is False  # type: ignore[arg-type]
    assert spider._validate_url(123) is False  # type: ignore[arg-type]
