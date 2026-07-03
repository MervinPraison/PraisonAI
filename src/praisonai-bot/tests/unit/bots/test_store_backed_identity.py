"""Tests for the wrapper StoreBackedIdentityResolver.

A store-backed resolver maps ``(platform, user_id)`` to a canonical
identity using an explicit link map plus the gateway pairing store, with a
safe per-platform fallback for unlinked users.
"""

from __future__ import annotations

import os

import pytest

from praisonaiagents.session.identity import IdentityResolverProtocol


@pytest.fixture()
def resolver(tmp_path):
    from praisonai_bot.bots import StoreBackedIdentityResolver

    path = tmp_path / "identity.json"
    return StoreBackedIdentityResolver(path=path)


def test_exported_from_bots():
    from praisonai_bot.bots import StoreBackedIdentityResolver

    assert StoreBackedIdentityResolver is not None


def test_satisfies_protocol(resolver):
    assert isinstance(resolver, IdentityResolverProtocol)


def test_unlinked_returns_per_platform_fallback(resolver):
    assert resolver.resolve("telegram", "12345") == "telegram:12345"


def test_explicit_link_unifies_channels(resolver):
    resolver.link("telegram", "12345", "alice")
    resolver.link("whatsapp", "+44123", "alice")
    assert resolver.resolve("telegram", "12345") == "alice"
    assert resolver.resolve("whatsapp", "+44123") == "alice"


def test_unlink_reverts_to_fallback(resolver):
    resolver.link("telegram", "12345", "alice")
    resolver.unlink("telegram", "12345")
    assert resolver.resolve("telegram", "12345") == "telegram:12345"


def test_links_for_lists_all_channels(resolver):
    resolver.link("telegram", "12345", "alice")
    resolver.link("whatsapp", "+44123", "alice")
    links = resolver.links_for("alice")
    pairs = {(link.platform, link.platform_user_id) for link in links}
    assert pairs == {("telegram", "12345"), ("whatsapp", "+44123")}


def test_all_links_returns_every_mapping(resolver):
    resolver.link("telegram", "12345", "alice")
    resolver.link("whatsapp", "+44123", "alice")
    resolver.link("discord", "d1", "bob")
    assert set(resolver.all_links()) == {
        ("telegram", "12345", "alice"),
        ("whatsapp", "+44123", "alice"),
        ("discord", "d1", "bob"),
    }


def test_persists_across_instances(tmp_path):
    from praisonai_bot.bots import StoreBackedIdentityResolver

    path = tmp_path / "identity.json"
    r1 = StoreBackedIdentityResolver(path=path)
    r1.link("telegram", "12345", "alice")

    r2 = StoreBackedIdentityResolver(path=path)
    assert r2.resolve("telegram", "12345") == "alice"


def _make_pairing_store(tmp_path):
    from praisonai_bot.gateway.pairing import PairingStore

    store_dir = str(tmp_path / "gateway")
    os.makedirs(store_dir, exist_ok=True)
    return PairingStore(store_dir=store_dir)


def test_pairing_label_resolves_canonical(tmp_path):
    from praisonai_bot.bots import StoreBackedIdentityResolver

    pairing = _make_pairing_store(tmp_path)
    code = pairing.generate_code(channel_type="telegram", channel_id="u1")
    assert pairing.verify_and_pair(code, "u1", "telegram", label="alice")

    resolver = StoreBackedIdentityResolver(
        path=tmp_path / "identity.json", pairing_store=pairing
    )
    assert resolver.resolve("telegram", "u1") == "alice"
    # Unpaired user still falls back.
    assert resolver.resolve("telegram", "u2") == "telegram:u2"


def test_explicit_link_overrides_pairing(tmp_path):
    from praisonai_bot.bots import StoreBackedIdentityResolver

    pairing = _make_pairing_store(tmp_path)
    code = pairing.generate_code(channel_type="telegram", channel_id="u1")
    pairing.verify_and_pair(code, "u1", "telegram", label="alice")

    resolver = StoreBackedIdentityResolver(
        path=tmp_path / "identity.json", pairing_store=pairing
    )
    resolver.link("telegram", "u1", "bob")
    assert resolver.resolve("telegram", "u1") == "bob"


def test_link_paired_materialises_links(tmp_path):
    from praisonai_bot.bots import StoreBackedIdentityResolver

    pairing = _make_pairing_store(tmp_path)
    for ch_id in ("u1", "u2"):
        code = pairing.generate_code(channel_type="telegram", channel_id=ch_id)
        pairing.verify_and_pair(code, ch_id, "telegram", label="alice")

    resolver = StoreBackedIdentityResolver(
        path=tmp_path / "identity.json", pairing_store=pairing
    )
    count = resolver.link_paired()
    assert count == 2
    assert resolver.resolve("telegram", "u1") == "alice"
    assert resolver.resolve("telegram", "u2") == "alice"


def test_from_env_degrades_without_pairing(tmp_path, monkeypatch):
    import sys

    from praisonai_bot.bots import StoreBackedIdentityResolver

    # Force the optional pairing import to fail so the ``except`` degraded
    # branch in from_env() is actually exercised. Pass an explicit ``path``
    # (the default is captured at import time, so setenv would not apply).
    monkeypatch.delitem(sys.modules, "praisonai_bot.gateway.pairing", raising=False)
    monkeypatch.setitem(sys.modules, "praisonai_bot.gateway.pairing", None)
    resolver = StoreBackedIdentityResolver.from_env(
        path=str(tmp_path / "identity.json"), store_dir=str(tmp_path / "gw")
    )
    assert resolver._pairing_store is None
    # Works as a plain resolver when pairing is unavailable.
    assert resolver.resolve("telegram", "x") == "telegram:x"
    resolver.link("telegram", "x", "alice")
    assert resolver.resolve("telegram", "x") == "alice"
