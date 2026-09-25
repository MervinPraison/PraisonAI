"""Unit tests for trusted-proxy ingress attribution (Issue #5312).

Covers the pure, core-side contract: :func:`parse_forwarded_for`,
:func:`resolve_ingress_attribution`, and the :class:`IngressAttribution`
dataclass. No I/O — the trust decision must fail closed for anything
proxy-shaped but unattributable, and resolve the real client only across
operator-declared trusted hops.
"""

from praisonaiagents.gateway import (
    IngressAttribution,
    parse_forwarded_for,
    resolve_ingress_attribution,
)


def test_parse_forwarded_for_splits_and_trims():
    assert parse_forwarded_for("1.2.3.4, 10.0.0.1 , 10.0.0.2") == [
        "1.2.3.4",
        "10.0.0.1",
        "10.0.0.2",
    ]


def test_parse_forwarded_for_empty():
    assert parse_forwarded_for(None) == []
    assert parse_forwarded_for("") == []
    assert parse_forwarded_for(" , ") == []


def test_direct_local_no_headers():
    attr = resolve_ingress_attribution(peer_ip="127.0.0.1")
    assert attr == IngressAttribution(
        trust="direct-local", client_ip="127.0.0.1", via_proxy=False, fail_closed=False
    )


def test_direct_remote_no_headers():
    attr = resolve_ingress_attribution(peer_ip="203.0.113.9")
    assert attr.trust == "direct-remote"
    assert attr.client_ip == "203.0.113.9"
    assert attr.via_proxy is False
    assert attr.fail_closed is False


def test_unattributable_proxy_fails_closed():
    # Directly-reachable gateway: an attacker sets X-Forwarded-For but the peer
    # is not a declared trusted proxy -> never trust the header, key on peer.
    attr = resolve_ingress_attribution(
        peer_ip="203.0.113.9",
        forwarded_for=["1.1.1.1"],
        trusted_proxies=[],
    )
    assert attr.trust == "unattributable-proxy"
    assert attr.client_ip == "203.0.113.9"
    assert attr.via_proxy is True
    assert attr.fail_closed is True


def test_untrusted_peer_with_trusted_set_still_fails_closed():
    attr = resolve_ingress_attribution(
        peer_ip="203.0.113.9",
        forwarded_for=["1.1.1.1"],
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.trust == "unattributable-proxy"
    assert attr.fail_closed is True
    assert attr.client_ip == "203.0.113.9"


def test_trusted_proxy_resolves_real_client():
    attr = resolve_ingress_attribution(
        peer_ip="10.0.0.5",
        forwarded_for=["203.0.113.9", "10.0.0.5"],
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.trust == "trusted-proxy"
    assert attr.client_ip == "203.0.113.9"
    assert attr.via_proxy is True
    assert attr.fail_closed is False


def test_trusted_proxy_peels_chain_to_first_untrusted():
    # Two trusted hops appended; the real client is the first untrusted address
    # walking right->left.
    attr = resolve_ingress_attribution(
        peer_ip="10.0.0.1",
        forwarded_for=["198.51.100.7", "10.0.0.2", "10.0.0.1"],
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.client_ip == "198.51.100.7"
    assert attr.trust == "trusted-proxy"


def test_spoofed_prefix_not_peeled_past_untrusted_hop():
    # An attacker prepends a spoofed trusted-looking address; because the first
    # untrusted hop stops the walk, the spoof cannot masquerade as the client.
    attr = resolve_ingress_attribution(
        peer_ip="10.0.0.1",
        forwarded_for=["10.0.0.9", "198.51.100.7", "10.0.0.1"],
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.client_ip == "198.51.100.7"


def test_bare_ip_trusted_entry():
    attr = resolve_ingress_attribution(
        peer_ip="192.168.1.10",
        forwarded_for=["203.0.113.9", "192.168.1.10"],
        trusted_proxies=["192.168.1.10"],
    )
    assert attr.trust == "trusted-proxy"
    assert attr.client_ip == "203.0.113.9"


def test_tunnel_classification_for_loopback_trusted_hop():
    # A loopback sidecar tunnel (Tailscale/Cloudflare) declared trusted.
    attr = resolve_ingress_attribution(
        peer_ip="127.0.0.1",
        forwarded_for=["203.0.113.9"],
        trusted_proxies=["127.0.0.1"],
        real_ip=None,
    )
    assert attr.trust == "tunnel"
    assert attr.client_ip == "203.0.113.9"
    assert attr.fail_closed is False


def test_real_ip_used_when_chain_all_trusted():
    attr = resolve_ingress_attribution(
        peer_ip="10.0.0.5",
        forwarded_for=["10.0.0.6", "10.0.0.5"],
        real_ip="203.0.113.9",
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.client_ip == "203.0.113.9"


def test_real_ip_only_with_trusted_peer():
    attr = resolve_ingress_attribution(
        peer_ip="10.0.0.5",
        forwarded_for=[],
        real_ip="203.0.113.9",
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.trust == "trusted-proxy"
    assert attr.client_ip == "203.0.113.9"


def test_real_ip_only_untrusted_peer_fails_closed():
    attr = resolve_ingress_attribution(
        peer_ip="203.0.113.9",
        forwarded_for=[],
        real_ip="1.1.1.1",
        trusted_proxies=["10.0.0.0/8"],
    )
    assert attr.fail_closed is True
    assert attr.client_ip == "203.0.113.9"
