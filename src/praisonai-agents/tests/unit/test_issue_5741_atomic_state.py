"""Issue #5741 Gap 3: persisted state writes must not clobber prior content."""

import json
import logging

from praisonaiagents.knowledge.indexing import FileTracker
from praisonaiagents.rag.summarizer import (
    HierarchicalSummarizer,
    HierarchyResult,
    SummaryNode,
)


def test_summarizer_failed_save_keeps_previous_hierarchy(tmp_path, caplog):
    s = HierarchicalSummarizer(persist_path=str(tmp_path))
    good = HierarchyResult(root_path="/c", total_files=1)
    good.nodes["a"] = SummaryNode(path="a", level=1, summary="ok")
    s._save_hierarchy("/c", good)
    assert s._load_hierarchy("/c").nodes["a"].summary == "ok"

    bad = HierarchyResult(root_path="/c", built_at=object())  # not JSON-serialisable
    with caplog.at_level(logging.WARNING):
        s._save_hierarchy("/c", bad)

    loaded = s._load_hierarchy("/c")
    assert loaded is not None and loaded.nodes["a"].summary == "ok"
    assert "Failed to save hierarchy" in caplog.text


def test_file_tracker_warns_on_corrupt_state(tmp_path, caplog):
    state = tmp_path / "state.json"
    state.write_text("{truncated", encoding="utf-8")
    t = FileTracker(state_file=str(state))
    with caplog.at_level(logging.WARNING):
        t.load()
    assert t._tracked == {}
    assert "re-indexing" in caplog.text


def test_file_tracker_roundtrip(tmp_path):
    state = tmp_path / "state.json"
    t = FileTracker(state_file=str(state))
    t._tracked = {"f.py": {"hash": "x"}}
    t.save()
    assert json.loads(state.read_text(encoding="utf-8")) == {"f.py": {"hash": "x"}}
