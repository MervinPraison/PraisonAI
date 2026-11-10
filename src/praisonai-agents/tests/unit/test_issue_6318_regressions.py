"""Regression tests for issue #6318."""

from pathlib import Path

import pytest

from praisonaiagents.compaction.compactor import CompactionStrategy, ContextCompactor
from praisonaiagents.context.artifact_store import FileSystemArtifactStore
from praisonaiagents.context.artifacts import ArtifactMetadata
from praisonaiagents.rag.compressor import ContextCompressor


@pytest.mark.parametrize("strategy", [CompactionStrategy.TRUNCATE, CompactionStrategy.SLIDING])
@pytest.mark.parametrize("with_system", [True, False])
def test_compaction_keeps_newest_message(strategy, with_system):
    c = ContextCompactor(max_tokens=200, strategy=strategy, preserve_recent=2)
    msgs = [{"role": "system", "content": "You are helpful."}] if with_system else []
    big = "BIG PASTE " * 400
    msgs += [
        {"role": "user", "content": "hi " * 50},
        {"role": "assistant", "content": "ok " * 50},
        {"role": "user", "content": big},
    ]
    out, _ = c.compact(msgs)
    assert out[-1] == {"role": "user", "content": big}


def test_artifact_store_stays_inside_root(tmp_path):
    root = tmp_path / "store"
    store = FileSystemArtifactStore(base_dir=str(root))
    meta = ArtifactMetadata(agent_id="../../outside", run_id="../r1", tool_name="t", turn_id=1)
    ref = store.store("hello", meta)
    assert (tmp_path / "store").resolve() in Path(ref.path).resolve().parents
    assert not (tmp_path / "outside").exists()
    assert store.load(ref) == "hello"
    assert len(store.list_artifacts(agent_id="../../outside", run_id="../r1")) == 1


def test_rag_dedup_keeps_chunks_sharing_long_prefix():
    hdr = "Acme Corp Employee Handbook - Confidential. Revision 12. " * 5
    chunks = [
        {"text": hdr + "Refunds: 30 days."},
        {"text": hdr + "Security: rotate passwords."},
        {"text": hdr + "Leave: 25 days."},
        {"text": "  " + hdr.upper() + "Leave:   25 days.  "},  # exact dup after normalising
    ]
    assert len(ContextCompressor()._deduplicate(chunks)) == 3
