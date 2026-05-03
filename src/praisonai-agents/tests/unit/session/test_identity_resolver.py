"""Tests for IdentityResolverProtocol and InMemoryIdentityResolver.

W1 — Cross-platform identity linking. An IdentityResolver maps
``(platform, platform_user_id)`` → ``unified_user_id`` so that the same
human can be recognised across Telegram, Discord, Slack, etc.

Linking is OPT-IN. By default the resolver returns the platform-prefixed
ID unchanged (no surprises, no privacy leak).
"""

from __future__ import annotations

import pytest

from praisonaiagents.session.identity import (
    IdentityLink,
    IdentityResolverProtocol,
    InMemoryIdentityResolver,
)


class TestIdentityLink:
    def test_link_holds_platform_user_unified(self):
        link = IdentityLink(
            platform="telegram",
            platform_user_id="12345",
            unified_user_id="alice",
        )
        assert link.platform == "telegram"
        assert link.platform_user_id == "12345"
        assert link.unified_user_id == "alice"

    def test_link_is_immutable(self):
        link = IdentityLink("telegram", "12345", "alice")
        with pytest.raises((AttributeError, Exception)):
            link.unified_user_id = "bob"  # type: ignore[misc]


class TestProtocolConformance:
    def test_in_memory_satisfies_protocol(self):
        resolver = InMemoryIdentityResolver()
        assert isinstance(resolver, IdentityResolverProtocol)

    def test_protocol_has_required_methods(self):
        proto_methods = {"resolve", "link", "unlink", "links_for"}
        assert proto_methods.issubset(set(dir(IdentityResolverProtocol)))


class TestInMemoryResolverDefaults:
    def test_unlinked_returns_platform_prefixed_id(self):
        """When no link exists, return ``{platform}:{user_id}`` unchanged."""
        r = InMemoryIdentityResolver()
        assert r.resolve("telegram", "12345") == "telegram:12345"

    def test_unlinked_does_not_create_link(self):
        r = InMemoryIdentityResolver()
        r.resolve("telegram", "12345")
        assert r.links_for("telegram:12345") == []


class TestLinking:
    def test_link_two_platforms_resolves_to_same_unified(self):
        r = InMemoryIdentityResolver()
        r.link("telegram", "12345", "alice")
        r.link("discord", "snowflake-1", "alice")
        assert r.resolve("telegram", "12345") == "alice"
        assert r.resolve("discord", "snowflake-1") == "alice"

    def test_unlink_reverts_to_default(self):
        r = InMemoryIdentityResolver()
        r.link("telegram", "12345", "alice")
        r.unlink("telegram", "12345")
        assert r.resolve("telegram", "12345") == "telegram:12345"

    def test_links_for_returns_all_platforms(self):
        r = InMemoryIdentityResolver()
        r.link("telegram", "12345", "alice")
        r.link("discord", "snowflake-1", "alice")
        links = r.links_for("alice")
        assert len(links) == 2
        platforms = {link.platform for link in links}
        assert platforms == {"telegram", "discord"}

    def test_link_overwrites_previous(self):
        r = InMemoryIdentityResolver()
        r.link("telegram", "12345", "alice")
        r.link("telegram", "12345", "bob")
        assert r.resolve("telegram", "12345") == "bob"


class TestThreadSafety:
    def test_concurrent_links_dont_corrupt_state(self):
        import threading

        r = InMemoryIdentityResolver()

        def worker(i):
            r.link("telegram", f"u{i}", f"unified-{i}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(50):
            assert r.resolve("telegram", f"u{i}") == f"unified-{i}"
