"""Tests for the default structured summary builder.

Un-stubs the documented ``structured_template=True`` compaction feature: the
builder must render ``SUMMARY_TEMPLATE``'s section headers, preserve file paths
verbatim, and never raise (falling back to a plain summary on failure).
"""

from praisonaiagents.compaction import (
    ContextCompactor,
    CompactionConfig,
    DefaultSummaryBuilder,
)


_HEADERS = [
    "## Active Task",
    "## Completed Actions",
    "## In Progress",
    "## Pending Questions",
    "## Relevant Files / Paths",
    "## Remaining Work",
]


def _conversation():
    return [
        {"role": "system", "content": "You are a helpful agent."},
        {"role": "user", "content": "Refactor src/app/main.py to add logging."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "content": "contents of src/app/main.py"},
        {"role": "assistant", "content": "Should I also update tests/test_main.py?"},
        {"role": "user", "content": "Yes, update tests/test_main.py too."},
    ]


def test_output_contains_all_template_headers():
    builder = DefaultSummaryBuilder()
    out = builder.build_structured_summary(_conversation())
    for header in _HEADERS:
        assert header in out


def test_preserves_file_paths_verbatim():
    builder = DefaultSummaryBuilder()
    out = builder.build_structured_summary(_conversation())
    assert "src/app/main.py" in out
    assert "tests/test_main.py" in out


def test_captures_active_task_and_tool_call():
    builder = DefaultSummaryBuilder()
    out = builder.build_structured_summary(_conversation())
    assert "Refactor src/app/main.py" in out
    assert "read_file" in out


def test_never_raises_falls_back_to_plain_summary():
    builder = DefaultSummaryBuilder()
    # Malformed messages (None content, non-dict entries) must not raise.
    bad = [None, {"role": "user", "content": None}, 42]  # type: ignore
    out = builder.build_structured_summary(bad)  # type: ignore[arg-type]
    assert isinstance(out, str) and out


def test_merge_summaries_keeps_both():
    builder = DefaultSummaryBuilder()
    merged = builder.merge_summaries("PREV", "CUR")
    assert "PREV" in merged and "CUR" in merged
    assert builder.merge_summaries("", "CUR") == "CUR"
    assert builder.merge_summaries("PREV", "") == "PREV"


def test_compactor_defaults_builder_when_structured_template():
    compactor = ContextCompactor(config=CompactionConfig(structured_template=True))
    assert compactor.summary_builder is not None
    out = compactor._build_structured_summary(_conversation())
    assert "## Active Task" in out
    # No longer the one-line stub.
    assert not out.startswith("Summary of ")


def test_compactor_no_builder_when_disabled():
    compactor = ContextCompactor(
        config=CompactionConfig(structured_template=False)
    )
    assert compactor.summary_builder is None
    out = compactor._build_structured_summary(_conversation())
    assert out.startswith("Summary of ")
