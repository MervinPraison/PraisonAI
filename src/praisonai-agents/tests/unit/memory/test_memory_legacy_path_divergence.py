"""`Memory` must not fall through to legacy SQL that bypasses the active adapter.

Two public methods still target the pre-adapter schema:

* `get_all_memories()` selects from `short_mem` / `long_mem`. Nothing in the
  codebase creates those tables -- the adapter creates `short_term_memory` /
  `long_term_memory` -- so the OperationalError is swallowed and it returns []
  for every provider, always.
* `delete_memory(id)` with no `memory_type` returns on the first tier that
  reports a hit. The SQLite adapter gives each tier its own AUTOINCREMENT
  sequence, so the Nth short-term row and the Nth long-term row always share an
  id. Deleting the id `remember()` handed back therefore destroys an unrelated
  short-term row and leaves the caller's target in place, returning success.

Sibling methods (`delete_short_term`, `reset_short_term`) already delegate to the
adapter with explicit comments saying why; these two were missed.
"""
import pytest

from praisonaiagents.memory.memory import Memory


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A Memory backed by a SQLite store isolated to this test.

    The adapter resolves its database under ``./.praisonai``, so isolation means
    changing the working directory -- passing ``storage_path`` in the config does
    not move it, and without the chdir every test shares one store.
    """
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return Memory(config={"provider": "sqlite"})


def _tier(mem, which):
    return [r for r in mem.memory_adapter.get_all_memories()
            if (r.get("memory_type") or r.get("type")) == which]


def test_adapter_holds_the_data(store):
    """Control: without this passing, the other assertions prove nothing."""
    store.store_short_term("STM: user prefers dark mode")
    store.store_long_term("LTM: user is in Chennai")
    assert len(store.memory_adapter.get_all_memories()) == 2


def test_get_all_memories_returns_what_is_stored(store):
    store.store_short_term("STM: user prefers dark mode")
    store.store_long_term("LTM: user is in Chennai")

    got = store.get_all_memories()
    assert got, (
        "get_all_memories() returned nothing while the adapter holds "
        f"{len(store.memory_adapter.get_all_memories())} rows"
    )
    kinds = {r.get("memory_type") or r.get("type") for r in got}
    assert kinds == {"short_term", "long_term"}


def test_delete_by_id_erases_the_long_term_record(store):
    """The id `remember()` returns must delete the record it refers to."""
    short_id = store.store_short_term("turn 1: hello there")
    long_id = store.remember("User SSN is 123-45-6789")

    # Precondition. If the ids do not collide this test cannot detect the bug.
    assert short_id == long_id, (
        f"expected an id collision across tiers, got {short_id!r} / {long_id!r}"
    )

    store.forget(memory_id=long_id)

    assert _tier(store, "long_term") == [], (
        "the record the caller asked to erase is still present"
    )


def test_delete_without_collision_still_works(store):
    """Control: the no-collision case must keep behaving as before."""
    long_id = store.remember("SECRET fact")
    assert store.forget(memory_id=long_id) == 1
    assert _tier(store, "long_term") == []
