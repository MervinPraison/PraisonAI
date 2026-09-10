"""Memory writes carry a provenance/trust signal and recall can be gated on it.

Untrusted external input (e.g. a gateway bot ingesting a group-chat message)
must not be silently recalled as trusted context. These tests verify:

* ``store_short_term`` / ``store_long_term`` stamp ``trust``/``origin`` into a
  dedicated metadata field the model cannot forge through prose.
* ``search_*`` with ``min_trust=TRUSTED`` fences out untrusted-origin content.
* Legacy writes (no trust field) are treated as trusted, so behaviour is
  backward compatible.
"""
import pytest

from praisonaiagents.memory import MemoryTrust
from praisonaiagents.memory.memory import Memory


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return Memory(config={"provider": "none"})


def test_trust_enum_ordering():
    assert MemoryTrust.rank(MemoryTrust.UNTRUSTED) < MemoryTrust.rank(MemoryTrust.TRUSTED)
    assert MemoryTrust.rank(MemoryTrust.TRUSTED) < MemoryTrust.rank(MemoryTrust.SYSTEM)
    # Unstamped writes default to trusted.
    assert MemoryTrust.rank(None) == MemoryTrust.rank(MemoryTrust.TRUSTED)


def test_store_stamps_trust_and_origin(store):
    store.store_long_term(
        "group chat instruction",
        trust=MemoryTrust.UNTRUSTED,
        origin="telegram:group:123",
    )
    results = store.search_long_term("group chat instruction", limit=5)
    assert results
    meta = results[0]["metadata"]
    assert meta.get("trust") == "untrusted"
    assert meta.get("origin") == "telegram:group:123"


def test_untrusted_long_term_excluded_when_min_trust_trusted(store):
    store.store_long_term("hostile backdoor payload", trust=MemoryTrust.UNTRUSTED)
    store.store_long_term("operator approved fact", trust=MemoryTrust.TRUSTED)

    assert len(store.search_long_term("backdoor", limit=5)) == 1
    gated = store.search_long_term("backdoor", limit=5, min_trust=MemoryTrust.TRUSTED)
    assert gated == []
    assert store.search_long_term("operator", limit=5, min_trust=MemoryTrust.TRUSTED)


def test_untrusted_short_term_excluded_when_min_trust_trusted(store):
    store.store_short_term("untrusted stm content", trust=MemoryTrust.UNTRUSTED)
    assert len(store.search_short_term("untrusted", limit=5)) == 1
    assert store.search_short_term("untrusted", limit=5, min_trust=MemoryTrust.TRUSTED) == []


def test_legacy_unstamped_write_treated_as_trusted(store):
    store.store_long_term("legacy fact without trust field")
    gated = store.search_long_term("legacy", limit=5, min_trust=MemoryTrust.TRUSTED)
    assert len(gated) == 1


def test_default_search_is_backward_compatible(store):
    store.store_long_term("untrusted item", trust=MemoryTrust.UNTRUSTED)
    store.store_long_term("trusted item", trust=MemoryTrust.TRUSTED)
    # No min_trust -> everything returned, as before.
    assert len(store.search_long_term("item", limit=5)) == 2
