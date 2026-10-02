"""Tests for the last-run trace pointer (issue #5622)."""

from praisonaiagents.trace import (
    load_last_run_pointer,
    record_completed_run,
    last_run_pointer_path,
)


def test_record_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}", encoding="utf-8")

    target = record_completed_run(trace, meta={"agent": "researcher"})
    assert target == last_run_pointer_path()
    assert target.exists()

    pointer = load_last_run_pointer()
    assert pointer is not None
    assert pointer["path"] == str(trace.resolve())
    assert pointer["meta"] == {"agent": "researcher"}


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    assert load_last_run_pointer() is None


def test_load_malformed_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    path = last_run_pointer_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_last_run_pointer() is None


def test_write_is_atomic_no_tmp_left(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}", encoding="utf-8")
    record_completed_run(trace)

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_latest_record_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    record_completed_run(first)
    record_completed_run(second)

    pointer = load_last_run_pointer()
    assert pointer["path"] == str(second.resolve())
