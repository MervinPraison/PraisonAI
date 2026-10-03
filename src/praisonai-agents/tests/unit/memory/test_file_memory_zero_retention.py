"""Compression must summarize records when no short-term items are retained."""

import pytest

from praisonaiagents.memory.file_memory import FileMemory


@pytest.mark.parametrize("limit", [1, 2, 3])
@pytest.mark.parametrize("use_llm", [False, True])
def test_auto_compression_with_small_positive_limit(tmp_path, limit, use_llm):
    memory = FileMemory(user_id="small-limit", base_path=tmp_path,
                        config={"short_term_limit": limit, "auto_promote": False})
    contents = [f"record {i}" for i in range(limit)]
    for content in contents:
        memory.add_short_term(content)
    prompts = []

    def summarize(prompt):
        prompts.append(prompt)
        return "All records summarized"

    summary = memory.auto_compress_if_needed(llm_func=summarize if use_llm else None)
    assert summary
    assert memory.get_stats()["short_term_count"] == 0
    summaries = memory.export()["long_term"]
    assert len(summaries) == 1
    assert summaries[0]["metadata"]["items_compressed"] == limit
    for content in contents:
        assert content in (prompts[0] if use_llm else summary)
    reopened = FileMemory(user_id="small-limit", base_path=tmp_path)
    assert reopened.get_stats()["short_term_count"] == 0
    assert reopened.export()["long_term"] == summaries
    next_result = reopened.auto_compress_if_needed()
    assert next_result == ("" if limit == 1 else None)
    assert reopened.get_stats()["long_term_count"] == 1


@pytest.mark.parametrize("keep", [0, 1, 3])
def test_explicit_retention_and_noop_boundary(tmp_path, keep):
    memory = FileMemory(user_id="explicit", base_path=tmp_path)
    for content in ("old", "middle", "new"):
        memory.add_short_term(content)
    summary = memory.compress(max_items=keep)
    exported = memory.export()
    assert len(exported["short_term"]) == keep
    if keep == 3:
        assert summary == ""
        assert exported["long_term"] == []
    else:
        assert exported["long_term"][0]["metadata"]["items_compressed"] == 3 - keep
        assert "old" in summary
        if keep == 1:
            assert exported["short_term"][0]["content"] == "new"


def test_empty_zero_retention_does_not_call_summarizer(tmp_path):
    memory = FileMemory(user_id="empty", base_path=tmp_path)

    def unexpected_call(prompt):
        pytest.fail("Empty memory should not call the summarizer")

    assert memory.compress(llm_func=unexpected_call, max_items=0) == ""
    assert memory.get_stats()["long_term_count"] == 0


def test_discarded_summary_preserves_source_records(tmp_path):
    memory = FileMemory(user_id="retention", base_path=tmp_path,
                        config={"long_term_limit": 1, "auto_promote": False})
    memory.add_long_term("essential", importance=1.0)
    memory.add_short_term("source")
    memory.compress(max_items=0)
    reopened = FileMemory(user_id="retention", base_path=tmp_path)
    assert [i["content"] for i in reopened.export()["short_term"]] == ["source"]
    assert [i["content"] for i in reopened.export()["long_term"]] == ["essential"]


def test_concurrent_snapshot_is_committed_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    memory = FileMemory(user_id="same-snapshot", base_path=tmp_path)
    memory.add_short_term("source")
    peer = FileMemory(user_id="same-snapshot", base_path=tmp_path)
    barrier = Barrier(2)

    def summarize(prompt):
        barrier.wait(timeout=5)
        return "summary"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(m.compress, summarize, 0) for m in (memory, peer)]
        for future in futures:
            future.result(timeout=10)
    reopened = FileMemory(user_id="same-snapshot", base_path=tmp_path)
    assert len(reopened.export()["long_term"]) == 1
    assert reopened.export()["short_term"] == []


@pytest.mark.parametrize("keep", [0, 1])
@pytest.mark.parametrize("peer_instance", [False, True])
def test_records_added_during_summary_are_retained(tmp_path, keep, peer_instance):
    memory = FileMemory(user_id="during-summary", base_path=tmp_path)
    for i in range(4):
        memory.add_short_term(f"original {i}")
    writer = FileMemory(user_id="during-summary", base_path=tmp_path) if peer_instance else memory

    def summarize(prompt):
        writer.add_short_term("added during summary")
        return prompt

    summary = memory.compress(llm_func=summarize, max_items=keep)
    reopened = FileMemory(user_id="during-summary", base_path=tmp_path)
    retained = [item["content"] for item in reopened.export()["short_term"]]
    expected = ["original 3", "added during summary"] if keep else ["added during summary"]
    assert retained == expected
    assert "added during summary" not in summary
    assert reopened.export()["long_term"][0]["metadata"]["items_compressed"] == 4 - keep


@pytest.mark.parametrize("keep", [0, 1])
def test_builtin_summary_preserves_all_selected_records(tmp_path, keep):
    memory = FileMemory(user_id="all-records", base_path=tmp_path)
    for i in range(8):
        memory.add_short_term(f"record {i}")
    summary = memory.compress(max_items=keep)
    for i in range(8 - keep):
        assert f"record {i}" in summary
    if keep:
        assert memory.export()["short_term"][0]["content"] == "record 7"
