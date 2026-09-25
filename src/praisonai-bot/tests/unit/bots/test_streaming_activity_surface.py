#!/usr/bin/env python3
"""
Tests for the opt-in, privacy-safe activity surface (issue #5314).

During an output-silent tool run in PROGRESS mode, an operator-configured
phrase keyed by tool *category* may be shown instead of the raw tool name.
Tool names/args/URLs are never surfaced when a catalogue is configured, and
behaviour is unchanged when it is not.
"""

from praisonai_bot.bots._streaming import (
    _SAFE_ACTIVITY_FALLBACK,
    DraftStreamer,
    StreamingConfig,
    StreamingMode,
    resolve_activity_category,
)


def _streamer(config: StreamingConfig) -> DraftStreamer:
    class _Adapter:
        capabilities = {"live_edit": True}

    s = DraftStreamer(_Adapter(), "chan", config, platform="telegram")
    s._message_id = "m1"
    return s


def test_resolve_activity_category_mappings():
    assert resolve_activity_category("web_search") == "web"
    assert resolve_activity_category("duckduckgo_search") == "search"
    assert resolve_activity_category("run_shell_command") == "shell"
    assert resolve_activity_category("python_interpreter") == "code"
    assert resolve_activity_category("read_file") == "file"
    assert resolve_activity_category("mcp_tool") == "mcp"


def test_resolve_activity_category_falls_back_to_default():
    assert resolve_activity_category("some_unmapped_tool") == "default"
    assert resolve_activity_category("") == "default"
    assert resolve_activity_category(None) == "default"


def test_activity_line_uses_curated_phrase_not_tool_name():
    cfg = StreamingConfig(
        mode=StreamingMode.PROGRESS,
        progress_prefix="",
        activity_phrases={
            "web": "Searching the web…",
            "shell": "Running a command…",
            "default": "Working on it…",
        },
    )
    s = _streamer(cfg)
    s._current_tool = "web_fetch_secret_url"
    content = s._render_content()
    assert content == "Searching the web…"
    # The raw tool name must never leak.
    assert "web_fetch_secret_url" not in content


def test_activity_line_default_phrase_for_unmapped_category():
    cfg = StreamingConfig(
        mode=StreamingMode.PROGRESS,
        progress_prefix="",
        activity_phrases={"default": "Working on it…"},
    )
    s = _streamer(cfg)
    s._current_tool = "totally_custom_tool"
    assert s._render_content() == "Working on it…"


def test_no_catalogue_preserves_legacy_behaviour():
    cfg = StreamingConfig(mode=StreamingMode.PROGRESS, progress_prefix="")
    s = _streamer(cfg)
    s._current_tool = "web_search"
    assert s._render_content() == "Running web_search..."


def test_from_dict_inline_activity_phrases():
    cfg = StreamingConfig.from_dict(
        {"mode": "progress", "activity_phrases": {"web": "Searching…"}}
    )
    assert cfg.activity_phrases == {"web": "Searching…"}


def test_from_dict_activity_status_block_enabled():
    cfg = StreamingConfig.from_dict(
        {
            "mode": "progress",
            "activity_status": {
                "enabled": True,
                "phrases": {"web": "Searching the web…", "default": "Working…"},
            },
        }
    )
    assert cfg.activity_phrases == {
        "web": "Searching the web…",
        "default": "Working…",
    }


def test_from_dict_activity_status_disabled_yields_none():
    cfg = StreamingConfig.from_dict(
        {
            "mode": "progress",
            "activity_status": {"enabled": False, "phrases": {"web": "x"}},
        }
    )
    assert cfg.activity_phrases is None


def test_from_dict_defaults_to_none():
    cfg = StreamingConfig.from_dict({"mode": "progress"})
    assert cfg.activity_phrases is None


def test_partial_catalogue_never_leaks_tool_name():
    # Catalogue enabled but missing both the matched category AND a default:
    # opting in must fall back to a safe generic line, NOT the raw tool name.
    cfg = StreamingConfig(
        mode=StreamingMode.PROGRESS,
        progress_prefix="",
        activity_phrases={"web": "Searching the web…"},
    )
    s = _streamer(cfg)
    s._current_tool = "run_shell_command"
    content = s._render_content()
    assert content == _SAFE_ACTIVITY_FALLBACK
    assert "run_shell_command" not in content


def test_schema_retains_activity_status_and_forwards_to_config():
    # The bot/gateway streaming schema must not silently drop the documented
    # activity_status block; it must survive validation and reach from_dict.
    from praisonai_bot.bots._config_schema import StreamingConfigSchema

    schema = StreamingConfigSchema(
        mode="progress",
        activity_status={
            "enabled": True,
            "phrases": {"web": "Searching the web…", "default": "Working…"},
        },
    )
    assert schema.activity_status is not None
    cfg = StreamingConfig.from_dict(schema.model_dump())
    assert cfg.activity_phrases == {
        "web": "Searching the web…",
        "default": "Working…",
    }


def test_feed_style_does_not_bypass_curated_phrases():
    # In feed style with a catalogue enabled, the raw feed (which folds tool
    # names/summaries) must NOT be rendered; the curated line is shown instead.
    cfg = StreamingConfig(
        mode=StreamingMode.PROGRESS,
        progress_prefix="",
        progress_style="feed",
        activity_phrases={"web": "Searching the web…", "default": "Working…"},
    )
    s = _streamer(cfg)
    s._current_tool = "web_fetch"
    # Simulate a populated feed carrying a raw tool name.
    s._progress_lines = ["run_shell_command: rm -rf /secret"]
    content = s._render_content()
    assert content == "Searching the web…"
    assert "run_shell_command" not in content
    assert "secret" not in content
