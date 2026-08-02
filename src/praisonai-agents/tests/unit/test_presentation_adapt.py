"""Tests for capability-aware presentation adaptation (adapt_presentation)."""

from praisonaiagents.bots import (
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    PresentationLimits,
    SelectOption,
    ActionType,
    BlockType,
    adapt_presentation,
    table_to_markdown,
    chart_to_text,
)


def _buttons_block(n):
    buttons = [PresentationButton(label=f"opt {i}", priority=i) for i in range(n)]
    return MessagePresentation([PresentationBlock.make_buttons(buttons)])


def test_priority_truncation_keeps_highest_priority():
    p = _buttons_block(12)
    adapted = adapt_presentation(p, PresentationLimits.slack())  # cap = 5
    kept = [b.label for b in adapted.blocks[0].buttons]
    assert kept == ["opt 7", "opt 8", "opt 9", "opt 10", "opt 11"]


def test_input_presentation_not_mutated():
    p = _buttons_block(12)
    adapt_presentation(p, PresentationLimits.slack())
    assert len(p.blocks[0].buttons) == 12


def test_label_truncated_to_max_button_label():
    p = MessagePresentation([
        PresentationBlock.make_buttons([PresentationButton(label="x" * 200, priority=1)])
    ])
    adapted = adapt_presentation(p, PresentationLimits.slack())
    assert len(adapted.blocks[0].buttons[0].label) == 75


def test_select_converted_to_buttons_when_unsupported():
    sel = PresentationBlock.make_select(
        [SelectOption(label="A", value="a"), SelectOption(label="B", value="b")],
        action_id="pick",
    )
    adapted = adapt_presentation(MessagePresentation([sel]), PresentationLimits.telegram())
    assert adapted.blocks[0].type == BlockType.BUTTONS
    values = [b.action.value for b in adapted.blocks[0].buttons]
    assert values == ["select:pick:a", "select:pick:b"]


def test_select_preserved_when_supported():
    sel = PresentationBlock.make_select(
        [SelectOption(label="A", value="a")], action_id="pick"
    )
    adapted = adapt_presentation(MessagePresentation([sel]), PresentationLimits.slack())
    assert adapted.blocks[0].type == BlockType.SELECT


def test_options_truncated_to_max_options():
    opts = [SelectOption(label=f"o{i}", value=str(i)) for i in range(50)]
    sel = PresentationBlock.make_select(opts, action_id="pick")
    adapted = adapt_presentation(MessagePresentation([sel]), PresentationLimits.discord())
    assert len(adapted.blocks[0].options) == 25


def test_web_app_degraded_to_url_when_unsupported():
    wb = PresentationButton(
        label="app",
        action=PresentationAction(type=ActionType.WEB_APP, web_app_url="https://e.com"),
    )
    adapted = adapt_presentation(
        MessagePresentation([PresentationBlock.make_buttons([wb])]),
        PresentationLimits.slack(),
    )
    btn = adapted.blocks[0].buttons[0]
    assert btn.action.type == ActionType.URL
    assert btn.url == "https://e.com"


def test_web_app_preserved_when_supported():
    wb = PresentationButton(
        label="app",
        action=PresentationAction(type=ActionType.WEB_APP, web_app_url="https://e.com"),
    )
    adapted = adapt_presentation(
        MessagePresentation([PresentationBlock.make_buttons([wb])]),
        PresentationLimits.telegram(),
    )
    assert adapted.blocks[0].buttons[0].action.type == ActionType.WEB_APP


def test_under_cap_preserves_all_and_order():
    p = _buttons_block(3)
    adapted = adapt_presentation(p, PresentationLimits.slack())
    assert [b.label for b in adapted.blocks[0].buttons] == ["opt 0", "opt 1", "opt 2"]


def test_discord_priority_truncation_caps_at_25():
    p = _buttons_block(40)
    adapted = adapt_presentation(p, PresentationLimits.discord())  # cap = 5 * 5 = 25
    kept = adapted.blocks[0].buttons
    assert len(kept) == 25
    # Highest-priority buttons survive (opt 15..opt 39), original order preserved.
    assert kept[0].label == "opt 15"
    assert kept[-1].label == "opt 39"


def test_degraded_select_callback_unique_for_long_action_id():
    long_id = "a" * 80
    sel = PresentationBlock.make_select(
        [
            SelectOption(label="A", value="alpha" + "x" * 60),
            SelectOption(label="B", value="beta" + "y" * 60),
        ],
        action_id=long_id,
    )
    adapted = adapt_presentation(MessagePresentation([sel]), PresentationLimits.telegram())
    values = [b.action.value for b in adapted.blocks[0].buttons]
    assert all(len(v) <= 64 for v in values)
    assert values[0] != values[1]


def test_degraded_select_callback_unbounded_kept_raw():
    sel = PresentationBlock.make_select(
        [SelectOption(label="A", value="a"), SelectOption(label="B", value="b")],
        action_id="pick",
    )
    adapted = adapt_presentation(MessagePresentation([sel]), PresentationLimits.telegram())
    values = [b.action.value for b in adapted.blocks[0].buttons]
    assert values == ["select:pick:a", "select:pick:b"]


# --- TABLE / CHART blocks ---------------------------------------------------


def test_table_to_markdown_deterministic():
    md = table_to_markdown(
        ["Plan", "Price"], [["Free", "0"], ["Pro", "20"]]
    )
    assert md == (
        "| Plan | Price |\n"
        "| --- | --- |\n"
        "| Free | 0 |\n"
        "| Pro | 20 |"
    )


def test_table_to_markdown_pads_and_escapes():
    md = table_to_markdown(["A", "B"], [["x|y"], ["p", "q", "extra"]])
    lines = md.splitlines()
    # short row padded, long row trimmed to 2 cols, pipe escaped
    assert lines[2] == "| x\\|y |  |"
    assert lines[3] == "| p | q |"


def test_table_block_degrades_to_markdown_text_when_unsupported():
    tbl = PresentationBlock.make_table(
        ["Plan", "Price"], [["Free", "0"], ["Pro", "20"]]
    )
    adapted = adapt_presentation(MessagePresentation([tbl]), PresentationLimits.slack())
    block = adapted.blocks[0]
    assert block.type == BlockType.TEXT
    assert block.text.startswith("| Plan | Price |")


def test_table_block_preserved_when_supported():
    limits = PresentationLimits.slack()
    limits.supports_tables = True
    tbl = PresentationBlock.make_table(["A"], [["1"], ["2"]])
    adapted = adapt_presentation(MessagePresentation([tbl]), limits)
    assert adapted.blocks[0].type == BlockType.TABLE
    assert adapted.blocks[0].rows == [["1"], ["2"]]


def test_table_clamped_to_row_and_col_caps_when_supported():
    limits = PresentationLimits(
        supports_tables=True, max_table_rows=2, max_table_cols=2
    )
    tbl = PresentationBlock.make_table(
        ["A", "B", "C"],
        [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]],
    )
    adapted = adapt_presentation(MessagePresentation([tbl]), limits)
    block = adapted.blocks[0]
    assert block.columns == ["A", "B"]
    assert block.rows == [["1", "2"], ["4", "5"]]


def test_chart_to_text_summary():
    summary = chart_to_text(
        "bar", [{"label": "Sign-ups", "points": [3, 5, 8]}]
    )
    assert summary == "Bar chart\nSign-ups: 3, 5, 8"


def test_chart_block_degrades_to_text_when_unsupported():
    chart = PresentationBlock.make_chart(
        "line", [{"label": "Views", "points": [1, 2, 3]}]
    )
    adapted = adapt_presentation(MessagePresentation([chart]), PresentationLimits.telegram())
    block = adapted.blocks[0]
    assert block.type == BlockType.TEXT
    assert "Views: 1, 2, 3" in block.text


def test_chart_block_preserved_when_supported():
    limits = PresentationLimits.slack()
    limits.supports_charts = True
    chart = PresentationBlock.make_chart("pie", [{"label": "x", "points": [1]}])
    adapted = adapt_presentation(MessagePresentation([chart]), limits)
    assert adapted.blocks[0].type == BlockType.CHART


def test_table_and_chart_roundtrip_serialization():
    p = MessagePresentation([
        PresentationBlock.make_table(["A"], [["1"]]),
        PresentationBlock.make_chart("bar", [{"label": "s", "points": [1, 2]}]),
    ])
    restored = MessagePresentation.from_dict(p.to_dict())
    assert restored.blocks[0].columns == ["A"]
    assert restored.blocks[0].rows == [["1"]]
    assert restored.blocks[1].chart_kind == "bar"
    assert restored.blocks[1].series == [{"label": "s", "points": [1, 2]}]
