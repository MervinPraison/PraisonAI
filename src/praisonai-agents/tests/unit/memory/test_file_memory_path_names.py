"""Caller-supplied names and dates must not escape the memory store (#5942)."""

import threading

import pytest

from praisonaiagents.memory import FileMemory
from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def memory(tmp_path):
    return FileMemory(user_id="u", base_path=str(tmp_path / "store"))


@pytest.mark.parametrize("date", ["../../../escaped", "2026-01-01/../x", "not-a-date"])
def test_episodic_date_must_be_a_plain_date(memory, tmp_path, date):
    with pytest.raises(ValueError):
        memory.add_episodic("pwn", date=date)
    assert not list(tmp_path.glob("**/escaped.json"))


@pytest.mark.parametrize("name", ["../../../../esc", "a/b", ".."])
def test_session_and_checkpoint_names_cannot_traverse(memory, name):
    with pytest.raises(ValueError):
        memory.save_session(name)
    with pytest.raises(ValueError):
        memory.create_checkpoint(name)


def test_plain_names_still_work(memory):
    memory.add_episodic("event", date="2026-01-01")
    assert [e.content for e in memory.get_episodic(date="2026-01-01")] == ["event"]
    assert memory.save_session("my session").endswith("my session.json")
    assert memory.create_checkpoint("ckpt-1") == "ckpt-1"


def test_unpadded_episodic_date_is_normalised(memory):
    memory.add_episodic("event", date="2026-3-5")
    assert [e.content for e in memory.get_episodic(date="2026-03-05")] == ["event"]
    assert (memory.episodic_path / "2026-03-05.json").exists()


def test_rule_name_cannot_traverse(tmp_path):
    with pytest.raises(ValueError):
        RulesManager(workspace_path=str(tmp_path)).create_rule("../../esc_rule", "x")
    assert not (tmp_path.parent / "esc_rule.md").exists()


def test_concurrent_episodic_adds_are_not_lost(memory):
    threads = [
        threading.Thread(target=memory.add_episodic, args=(f"event {i}",), kwargs={"date": "2026-01-01"})
        for i in range(40)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(memory.get_episodic(date="2026-01-01")) == 40
