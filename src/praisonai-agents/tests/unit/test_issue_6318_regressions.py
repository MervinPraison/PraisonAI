"""Regression tests for issue #6318."""

import json
import sys
from pathlib import Path

import pytest

from praisonaiagents.compaction.compactor import CompactionStrategy, ContextCompactor
from praisonaiagents.context.artifact_store import FileSystemArtifactStore
from praisonaiagents.context.artifacts import ArtifactMetadata
from praisonaiagents.rag.compressor import ContextCompressor


@pytest.mark.parametrize("strategy", [CompactionStrategy.TRUNCATE, CompactionStrategy.SLIDING])
@pytest.mark.parametrize("with_system", [True, False])
@pytest.mark.parametrize("preserve_recent", [0, 2])
def test_compaction_keeps_newest_message(strategy, with_system, preserve_recent):
    c = ContextCompactor(max_tokens=200, strategy=strategy, preserve_recent=preserve_recent)
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


def test_artifact_list_does_not_mix_colliding_ids(tmp_path):
    store = FileSystemArtifactStore(base_dir=str(tmp_path))
    store.store("a", ArtifactMetadata(agent_id="team/researcher", run_id="r", tool_name="t", turn_id=1))
    store.store("b", ArtifactMetadata(agent_id="team_researcher", run_id="r", tool_name="t", turn_id=1))
    refs = store.list_artifacts(agent_id="team/researcher")
    assert [r.agent_id for r in refs] == ["team/researcher"]
    assert len(store.list_artifacts(agent_id="team_researcher", run_id="r")) == 1
    assert len(store.list_artifacts(run_id="r")) == 2


def test_artifact_list_finds_legacy_unsanitised_dirs(tmp_path):
    store = FileSystemArtifactStore(base_dir=str(tmp_path))
    ref = store.store("x", ArtifactMetadata(agent_id="Research_Agent", run_id="run 1", tool_name="t", turn_id=1))
    # Simulate a pre-upgrade layout: raw names on disk and in metadata.
    legacy = tmp_path / "Research Agent" / "run 1"
    legacy.mkdir(parents=True)
    src = Path(ref.path)
    meta = src.with_suffix(".meta.json")
    (legacy / src.name).write_bytes(src.read_bytes())
    (legacy / meta.name).write_text(meta.read_text().replace('"Research_Agent"', '"Research Agent"'))
    refs = store.list_artifacts(agent_id="Research Agent", run_id="run 1")
    assert [r.agent_id for r in refs] == ["Research Agent"]


def test_rag_dedup_keeps_chunks_sharing_long_prefix():
    hdr = "Acme Corp Employee Handbook - Confidential. Revision 12. " * 5
    chunks = [
        {"text": hdr + "Refunds: 30 days."},
        {"text": hdr + "Security: rotate passwords."},
        {"text": hdr + "Leave: 25 days."},
        {"text": "  " + hdr.upper() + "Leave:   25 days.  "},  # exact dup after normalising
    ]
    assert len(ContextCompressor()._deduplicate(chunks)) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="':' is a drive separator on Windows, so the raw legacy dir can't be made under tmp_path")
def test_artifact_list_skips_drive_relative_legacy_names(tmp_path):
    # On Windows, root / "C:outside" is the drive-relative path "C:outside",
    # outside the store root, so an id with a colon is never tried as a raw,
    # pre-sanitization directory name; only its sanitized form "C_outside" is.
    store = FileSystemArtifactStore(base_dir=str(tmp_path))
    ref = store.store("x", ArtifactMetadata(agent_id="C_outside", run_id="r", tool_name="t", turn_id=1))
    raw = tmp_path / "C:outside" / "r"
    raw.mkdir(parents=True)
    src = Path(ref.path)
    meta = src.with_suffix(".meta.json")
    (raw / src.name).write_bytes(src.read_bytes())
    data = json.loads(meta.read_text())
    data["agent_id"] = "C:outside"
    (raw / meta.name).write_text(json.dumps(data))
    assert store.list_artifacts(agent_id="C:outside", run_id="r") == []
