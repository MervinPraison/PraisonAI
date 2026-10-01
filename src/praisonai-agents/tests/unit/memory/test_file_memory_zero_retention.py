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
