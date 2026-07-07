"""Tests for the WhatsApp presentation renderer and the renderer registry.

Issue #2747: portable presentations only rendered natively on
Telegram/Slack/Discord. These tests assert that WhatsApp now renders native
interactive reply buttons (<=3) and list messages (for overflow / selects),
and that a platform-keyed renderer registry (``render_for``) resolves renderers
uniformly with a plain-text fallback for channels without a native renderer.
"""

from praisonaiagents.bots.presentation import (
    ActionType,
    MessagePresentation,
    PresentationAction,
    PresentationBlock,
    PresentationButton,
    PresentationLimits,
    SelectOption,
)


def _approval_presentation():
    return MessagePresentation.approval("Allow file delete?", "appr-1")


class TestWhatsAppLimits:
    def test_limits_exist(self):
        limits = PresentationLimits.whatsapp()
        # 24 = list-row title budget; the renderer caps reply-button titles at
        # the tighter 20-char limit when it emits reply buttons.
        assert limits.max_button_label == 24
        assert limits.supports_select is True
        assert limits.supports_web_apps is False


class TestWhatsAppRenderer:
    def test_approval_renders_reply_buttons(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        rendered = WhatsAppPresentationRenderer.render(_approval_presentation())
        interactive = rendered["interactive"]
        assert interactive["type"] == "button"
        buttons = interactive["action"]["buttons"]
        # Allow Once / Deny -> 2 tappable reply buttons.
        assert len(buttons) == 2
        titles = [b["reply"]["title"] for b in buttons]
        assert "Allow Once" in titles
        assert "Deny" in titles
        # Command action ids are carried so a tap resolves the approval.
        ids = [b["reply"]["id"] for b in buttons]
        assert any("appr-1" in i for i in ids)

    def test_button_labels_capped_at_20(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_buttons([
                PresentationButton(
                    label="A very long button label indeed",
                    action=PresentationAction(type=ActionType.CALLBACK, value="x"),
                ),
            ]),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        title = rendered["interactive"]["action"]["buttons"][0]["reply"]["title"]
        assert len(title) <= 20

    def test_overflow_promotes_to_list(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        buttons = [
            PresentationButton(
                label=f"Opt{i}",
                action=PresentationAction(type=ActionType.CALLBACK, value=f"v{i}"),
            )
            for i in range(5)
        ]
        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_text("Choose"),
            PresentationBlock.make_buttons(buttons),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        interactive = rendered["interactive"]
        assert interactive["type"] == "list"
        rows = interactive["action"]["sections"][0]["rows"]
        assert len(rows) == 5

    def test_select_renders_list(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_text("Pick a plan"),
            PresentationBlock.make_select(
                [
                    SelectOption(label="Free", value="free"),
                    SelectOption(label="Pro", value="pro"),
                ],
                placeholder="Plans",
            ),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        interactive = rendered["interactive"]
        assert interactive["type"] == "list"
        rows = interactive["action"]["sections"][0]["rows"]
        assert {r["id"] for r in rows} == {"free", "pro"}

    def test_select_with_buttons_preserves_tappable_labels(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_text("Pick a plan"),
            PresentationBlock.make_select(
                [SelectOption(label="Free", value="free")],
                placeholder="Plans",
            ),
            PresentationBlock.make_buttons([
                PresentationButton(
                    label="Contact sales",
                    action=PresentationAction(type=ActionType.CALLBACK, value="sales"),
                ),
            ]),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        assert rendered["interactive"]["type"] == "list"
        # The tappable (non-URL) button must survive as readable text rather
        # than being silently dropped by the list path.
        assert "Contact sales" in rendered["interactive"]["body"]["text"]

    def test_url_button_inlined_not_dropped(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_text("Docs"),
            PresentationBlock.make_buttons([
                PresentationButton(
                    label="Open",
                    action=PresentationAction(
                        type=ActionType.URL, url="https://example.com"
                    ),
                ),
            ]),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        # A single url-only button cannot be a reply button; the link is kept
        # in the text rather than silently dropped.
        assert "interactive" not in rendered
        assert "https://example.com" in rendered["text"]

    def test_text_only_has_no_interactive(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
        )

        presentation = MessagePresentation(blocks=[
            PresentationBlock.make_text("Just text"),
        ])
        rendered = WhatsAppPresentationRenderer.render(presentation)
        assert "interactive" not in rendered
        assert rendered["text"] == "Just text"


class TestRendererRegistry:
    def test_registry_has_whatsapp(self):
        from praisonai_bot.bots._presentation_renderer import (
            WhatsAppPresentationRenderer,
            get_renderer,
        )

        assert get_renderer("whatsapp") is WhatsAppPresentationRenderer

    def test_render_for_whatsapp(self):
        from praisonai_bot.bots._presentation_renderer import render_for

        rendered = render_for("whatsapp", _approval_presentation())
        assert rendered["interactive"]["type"] == "button"

    def test_render_for_unknown_platform_falls_back_to_text(self):
        from praisonai_bot.bots._presentation_renderer import render_for

        rendered = render_for("email", _approval_presentation())
        assert "interactive" not in rendered
        # Buttons must survive as readable text, not be dropped.
        assert "Allow Once" in rendered["text"]
        assert "Deny" in rendered["text"]


class TestWhatsAppBotProtocol:
    def test_bot_exposes_presentation_methods(self):
        from praisonai_bot.bots.whatsapp import WhatsAppBot

        assert hasattr(WhatsAppBot, "render_presentation")
        assert hasattr(WhatsAppBot, "presentation_limits")
        assert hasattr(WhatsAppBot, "truncate_presentation")
