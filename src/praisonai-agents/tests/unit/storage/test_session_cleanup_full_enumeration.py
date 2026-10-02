"""Retention must include sessions beyond the listing display limit."""

import os
import time

import pytest

from praisonaiagents.storage.base import cleanup_old_sessions, list_json_sessions


@pytest.mark.parametrize("boundary", ["age", "size"])
@pytest.mark.parametrize("suffix", [".json", ".jsonl"])
def test_cleanup_includes_oldest_session_after_ten_thousand_newer_files(tmp_path, boundary, suffix):
    oldest = tmp_path / ("oldest" + suffix)
    oldest.write_bytes(b"x")
    now = time.time()
    old_time = now - 90 * 24 * 60 * 60
    os.utime(oldest, (old_time, old_time))
    for index in range(10000):
        (tmp_path / f"new-{index:05d}{suffix}").write_bytes(b"")
    neighbor = tmp_path / "unrelated.txt"
    neighbor.write_bytes(b"keep")

    if boundary == "age":
        deleted = cleanup_old_sessions(tmp_path, suffix=suffix, max_age_days=30, max_size_mb=100)
    else:
        # Only the oldest file contributes bytes to the quota; none exceed age.
        deleted = cleanup_old_sessions(tmp_path, suffix=suffix, max_age_days=365, max_size_mb=0)

    assert deleted == 1
    assert not oldest.exists()
    assert len(list(tmp_path.glob("new-*" + suffix))) == 10000
    assert neighbor.read_bytes() == b"keep"


def test_listing_keeps_default_limit_and_supports_unbounded_listing(tmp_path):
    for index in range(51):
        (tmp_path / f"session-{index:02d}.json").write_text("{}", encoding="utf-8")
    assert len(list_json_sessions(tmp_path)) == 50
    assert len(list_json_sessions(tmp_path, limit=3)) == 3
    assert len(list_json_sessions(tmp_path, limit=None)) == 51
