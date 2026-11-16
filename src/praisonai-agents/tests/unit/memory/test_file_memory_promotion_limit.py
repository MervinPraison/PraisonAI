"""Automatic promotion must honor the same capacity as explicit long-term writes."""

import json

import pytest
from praisonaiagents.memory.file_memory import FileMemory


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_promotion_enforces_persisted_long_term_limit(tmp_path, limit):
    memory = FileMemory(
        base_path=str(tmp_path),
        config={"short_term_limit": 2, "long_term_limit": limit},
    )
    for index in range(6):
        memory.add_short_term(f"Important fact {index}", importance=0.8)
    assert len(memory.get_long_term()) == limit
    assert len(FileMemory(base_path=str(tmp_path)).get_long_term()) == limit
    assert len(memory.get_short_term()) == 2


def test_promotion_keeps_highest_importance_and_newest_ties(tmp_path):
    memory = FileMemory(
        base_path=str(tmp_path),
        config={"short_term_limit": 3, "long_term_limit": 2},
    )
    memory.add_long_term("Keep strongest", importance=1.0)
    memory.add_long_term("Older tie", importance=0.8)
    memory.add_short_term("Lower priority", importance=0.7)
    memory.add_short_term("Newer tie", importance=0.8, metadata={"source": "fixture"})
    memory.add_short_term("Below promotion threshold", importance=0.2)
    for path, timestamp in [(memory.long_term_file, 100), (memory.short_term_file, 200)]:
        records = json.loads(path.read_text())
        for record in records:
            record["created_at"] = timestamp
        path.write_text(json.dumps(records))
    promoted_before = next(
        item for item in json.loads(memory.short_term_file.read_text())
        if item["content"] == "Newer tie"
    )
    memory.add_short_term("Trigger overflow", importance=0.2)
    contents = {item.content for item in memory.get_long_term()}
    assert contents == {"Keep strongest", "Newer tie"}
    promoted_after = next(item for item in memory.get_long_term() if item.content == "Newer tie")
    assert promoted_after.to_dict() == promoted_before
    assert {item.content for item in memory.get_short_term()} == {
        "Newer tie", "Below promotion threshold", "Trigger overflow",
    }
    assert {item.content for item in FileMemory(base_path=str(tmp_path)).get_long_term()} == contents


def test_disabled_promotion_preserves_existing_long_term(tmp_path):
    memory = FileMemory(
        base_path=str(tmp_path),
        config={"short_term_limit": 1, "long_term_limit": 1, "auto_promote": False},
    )
    memory.add_long_term("Existing fact")
    for index in range(3):
        memory.add_short_term(f"Unpromoted {index}", importance=1.0)
    assert [item.content for item in memory.get_long_term()] == ["Existing fact"]


def test_promotion_zero_capacity_matches_explicit_long_term(tmp_path):
    memory = FileMemory(
        base_path=str(tmp_path),
        config={"short_term_limit": 1, "long_term_limit": 0},
    )
    memory.add_long_term("Explicit fact", importance=1.0)
    assert memory.get_long_term() == []
    memory.add_short_term("Promoted one", importance=1.0)
    memory.add_short_term("Promoted two", importance=1.0)
    assert memory.get_long_term() == []
    assert FileMemory(base_path=str(tmp_path)).get_long_term() == []
