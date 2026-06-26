"""Tests for agent-authored interactive replies (presentation emit + reply route).

Covers the core seam added so an agent can emit a portable MessagePresentation
as a normal reply and have a button/select click routed back into the next turn.
"""

import asyncio

from praisonaiagents.bots import (
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    PresentationLimits,
    ActionType,
    BlockType,
    AgentReply,
    extract_presentation,
    adapt_presentation,
    encode_action,
    decode_callback,
    create_registry,
    make_reply_handler,
    InteractiveContext,
    REPLY_NAMESPACE,
)


def test_reply_action_factory():
    action = PresentationAction.reply("env=staging")
    assert action.type == ActionType.REPLY
    assert action.value == "env=staging"


def test_block_make_helpers():
    assert PresentationBlock.make_text("hi").type == BlockType.TEXT
    assert PresentationBlock.make_context("note").type == BlockType.CONTEXT
    assert PresentationBlock.make_buttons([]).type == BlockType.BUTTONS


def test_quick_replies_builds_reply_buttons():
    block = PresentationBlock.quick_replies([("Staging", "env=staging"), "Prod"])
    assert block.type == BlockType.BUTTONS
    assert block.buttons[0].action.type == ActionType.REPLY
    assert block.buttons[0].action.value == "env=staging"
    # Plain string choice uses itself as both label and value.
    assert block.buttons[1].label == "Prod"
    assert block.buttons[1].action.value == "Prod"


def test_encode_reply_action():
    enc = encode_action("ignored", PresentationAction.reply("pick=a"))
    assert enc == "reply:pick=a"
    namespace, payload = decode_callback(enc)
    assert namespace == REPLY_NAMESPACE
    assert payload["value"] == "pick=a"


def test_adapt_degrades_reply_to_callback():
    p = MessagePresentation([
        PresentationBlock.make_buttons([
            PresentationButton(label="Staging", action=PresentationAction.reply("env=staging")),
        ])
    ])
    adapted = adapt_presentation(p, PresentationLimits.telegram())
    btn = adapted.blocks[0].buttons[0]
    # Renderers only know command/callback/url/web_app; reply degrades to callback.
    assert btn.action.type == ActionType.CALLBACK
    assert btn.action.value == "reply:env=staging"


def test_adapt_reply_callback_respects_length_cap():
    long_value = "x" * 200
    p = MessagePresentation([
        PresentationBlock.make_buttons([
            PresentationButton(label="L", action=PresentationAction.reply(long_value)),
        ])
    ])
    adapted = adapt_presentation(p, PresentationLimits.telegram())
    val = adapted.blocks[0].buttons[0].action.value
    assert len(val) <= 64
    assert val.startswith("reply:")


def test_extract_presentation_plain_str():
    text, pres = extract_presentation("hello")
    assert text == "hello"
    assert pres is None


def test_extract_presentation_from_presentation():
    p = MessagePresentation([
        PresentationBlock.make_text("Which environment?"),
        PresentationBlock.quick_replies([("Staging", "staging")]),
    ])
    text, pres = extract_presentation(p)
    assert pres is p
    assert "Which environment?" in text


def test_extract_presentation_from_agent_reply():
    p = MessagePresentation([PresentationBlock.quick_replies([("A", "a")])])
    reply = AgentReply(text="Pick one", presentation=p)
    text, pres = extract_presentation(reply)
    assert text == "Pick one"
    assert pres is p


def test_extract_presentation_from_dict():
    p = MessagePresentation([PresentationBlock.make_text("hi")])
    data = AgentReply(text="t", presentation=p).to_dict()
    text, pres = extract_presentation(data)
    assert text == "t"
    assert isinstance(pres, MessagePresentation)
    assert pres.blocks[0].text == "hi"


def test_agent_reply_roundtrip():
    p = MessagePresentation([PresentationBlock.quick_replies([("A", "a")])])
    reply = AgentReply(text="hi", presentation=p)
    restored = AgentReply.from_dict(reply.to_dict())
    assert restored.text == "hi"
    assert restored.presentation.blocks[0].buttons[0].action.value == "a"


def test_reply_handler_routes_value_back_into_turn():
    seen = {}

    async def continue_turn(value, context):
        seen["value"] = value
        seen["user"] = context.user_id
        return f"ran with {value}"

    registry = create_registry()
    registry.register(REPLY_NAMESPACE, make_reply_handler(continue_turn))

    ctx = InteractiveContext(callback_data="reply:env=prod", user_id="u1")
    handled = asyncio.run(registry.dispatch(ctx))

    assert handled is True
    assert seen["value"] == "env=prod"
    assert seen["user"] == "u1"
