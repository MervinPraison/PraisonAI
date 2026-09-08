"""is_safe_http_url must not trust the resolver for ambiguous numeric hosts.

GHSA-5c6w-wwfq-7qqm is a parser differential, not a missing blocklist entry.
glibc's inet_aton reads a leading zero as OCTAL, so "0177.0.0.1" is 127.0.0.1
(loopback). getaddrinfo on macOS reads the same label as decimal and answers
177.0.0.1, an ordinary public address. is_safe_http_url classified the host by
asking getaddrinfo, so on macOS it returned True -- clearing a URL that an HTTP
client on glibc would connect to on loopback.

Every other encoding in the advisory (127.1, 0x7f000001, 2130706433) was already
blocked; only the dotted form with a non-decimal label slipped through, in both
this helper and SpiderTools._validate_url. They now share one check.
"""
import pytest

from praisonaiagents.tools.url_safety import (
    is_ambiguous_numeric_host,
    is_safe_http_url,
)


@pytest.mark.parametrize("host", [
    "0177.0.0.1",   # octal first label -> 127.0.0.1 under inet_aton
    "0x7f.0.0.1",   # hex label
    "127.0.01.1",   # leading zero in a later label
    "0300.0250.0.1",
])
def test_ambiguous_hosts_are_rejected(host):
    assert is_ambiguous_numeric_host(host) is True
    assert is_safe_http_url(f"http://{host}/") is False


@pytest.mark.parametrize("host", [
    "example.com",
    "1.1.1.1",
    "93.184.216.34",
    "0.0.0.0",        # unambiguous, and blocked on its own merits below
    "sub.domain.co",
])
def test_ordinary_hosts_are_not_treated_as_ambiguous(host):
    """The control: a check that rejects everything would also pass the test above."""
    assert is_ambiguous_numeric_host(host) is False


def test_canonical_loopback_still_blocked():
    assert is_safe_http_url("http://127.0.0.1/") is False


def test_public_host_still_allowed():
    assert is_safe_http_url("http://example.com/") is True
