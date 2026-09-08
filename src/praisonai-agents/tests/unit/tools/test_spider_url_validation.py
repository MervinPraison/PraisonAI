"""Regression tests for SSRF hardening in spider_tools._validate_url.

Covers GHSA-q9pw-vmhh-384g: a URL such as ``http://127.0.0.1:6666\\@1.1.1.1``
parses with hostname ``1.1.1.1`` via :func:`urllib.parse.urlparse` but is
dispatched to ``127.0.0.1`` by ``requests``. The validator must reject any
URL whose authority disagrees with the actual destination so that hostname
allow/deny checks cannot be smuggled past.
"""

import pytest

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


def test_blocks_the_octal_dotted_quad_that_the_resolver_reads_as_public():
    """The parser differential behind GHSA-5c6w-wwfq-7qqm.

    ``ipaddress.ip_address`` refuses ambiguous leading zeros, so ``0177.0.0.1``
    fell through to the resolver -- which reads it as the *public* 177.0.0.1
    and let it through. ``inet_aton`` (and every libc-based HTTP client) reads
    the same string as 127.0.0.1.
    """
    spider = SpiderTools()
    assert spider._validate_url("http://0177.0.0.1:8765/") is False


def _resolver_reads_as(host):
    """What the local resolver makes of ``host``, or None if it will not say."""
    import socket
    try:
        return socket.getaddrinfo(host, None)[0][4][0]
    except Exception:
        return None


def test_blocks_a_host_only_the_resolver_reads_as_private():
    """The differential also runs the other way, so both readings must count.

    ``010.0.0.1``: inet_aton reads the octal and yields the public 8.0.0.1,
    while the resolver yields the private 10.0.0.1. Trusting only inet_aton
    would reopen the hole from the other side.

    Which reading a resolver gives is a libc detail, so this asserts the
    contract only on a machine that actually exhibits the disagreement --
    rather than baking one platform's answer into CI.
    """
    if _resolver_reads_as("010.0.0.1") != "10.0.0.1":
        pytest.skip("local resolver does not read 010.0.0.1 as 10.0.0.1")
    spider = SpiderTools()
    assert spider._validate_url("http://010.0.0.1:8765/") is False


def test_a_trailing_dot_does_not_evade_the_check():
    spider = SpiderTools()
    assert spider._validate_url("http://0177.0.0.1.:8765/") is False


def test_ordinary_public_hosts_are_still_allowed():
    """The guard must not become a blanket deny."""
    spider = SpiderTools()
    assert spider._validate_url("https://example.com/path") is True
    assert spider._validate_url("http://1.1.1.1/") is True
