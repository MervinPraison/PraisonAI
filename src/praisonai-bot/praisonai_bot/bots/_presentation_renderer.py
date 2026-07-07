"""
Presentation rendering implementations for messaging platforms.

Converts portable MessagePresentation objects into platform-specific
interactive UI components (Telegram inline keyboards, Slack blocks, etc).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from praisonaiagents.bots.presentation import (
        MessagePresentation,
        PresentationBlock,
        PresentationButton,
        PresentationLimits,
        BlockType,
        ActionType,
    )

logger = logging.getLogger(__name__)


@runtime_checkable
class PresentationRenderer(Protocol):
    """Protocol every channel presentation renderer implements.

    A renderer converts a portable :class:`MessagePresentation` into a native,
    platform-specific payload. It must run ``adapt_presentation`` against its
    own :meth:`get_limits` before mapping blocks to native widgets so that
    capability-driven degradation (button overflow, unsupported selects/web
    apps, label truncation) is applied uniformly.
    """

    @staticmethod
    def get_limits() -> "PresentationLimits":
        """Return this channel's capability limits."""
        ...

    @staticmethod
    def render(presentation: "MessagePresentation") -> Dict[str, Any]:
        """Render *presentation* into a native, platform-specific payload."""
        ...


class TelegramPresentationRenderer:
    """Renders presentations as Telegram inline keyboards."""

    # Telegram limits callback_data to 64 *bytes* (UTF-8), not characters.
    _CALLBACK_MAX_BYTES = 64

    @staticmethod
    def _truncate_callback_data(value: str) -> str:
        """Truncate callback_data to Telegram's 64-byte UTF-8 limit.

        Slicing by characters can still exceed 64 bytes for non-ASCII input,
        which makes Telegram reject the whole inline keyboard. This truncates on
        a UTF-8 boundary so the payload always fits.
        """
        encoded = value.encode("utf-8")
        if len(encoded) <= TelegramPresentationRenderer._CALLBACK_MAX_BYTES:
            return value
        return encoded[: TelegramPresentationRenderer._CALLBACK_MAX_BYTES].decode(
            "utf-8", "ignore"
        )

    @staticmethod
    def get_limits() -> "PresentationLimits":
        """Get Telegram-specific presentation limits."""
        from praisonaiagents.bots.presentation import PresentationLimits
        return PresentationLimits.telegram()
    
    @staticmethod
    def render(presentation: "MessagePresentation") -> Dict[str, Any]:
        """Render a presentation for Telegram.
        
        Args:
            presentation: The presentation to render
            
        Returns:
            Dict with 'text' and optional 'reply_markup'
        """
        from praisonaiagents.bots.presentation import (
            BlockType,
            PresentationLimits,
            adapt_presentation,
        )
        
        presentation = adapt_presentation(presentation, PresentationLimits.telegram())
        
        text_parts = []
        inline_keyboard = []
        
        for block in presentation.blocks:
            if block.type == BlockType.TEXT or block.type == "text":
                if block.text:
                    text_parts.append(block.text)
            
            elif block.type == BlockType.CONTEXT or block.type == "context":
                if block.text:
                    text_parts.append(f"_{block.text}_")
            
            elif block.type == BlockType.DIVIDER or block.type == "divider":
                text_parts.append("—" * 20)
            
            elif block.type == BlockType.BUTTONS or block.type == "buttons":
                if block.buttons:
                    # Telegram allows multiple buttons per row
                    # We'll put up to 3 buttons per row for better layout
                    current_row = []
                    for button in block.buttons:
                        if len(current_row) >= 3:
                            inline_keyboard.append(current_row)
                            current_row = []
                        
                        # Label is pre-truncated by adapt_presentation()
                        label = button.label
                        
                        # Create button data based on action type
                        button_data = {"text": label}
                        
                        if button.url:
                            button_data["url"] = button.url
                        elif button.action:
                            if button.action.type == "url" and button.action.url:
                                button_data["url"] = button.action.url
                            elif button.action.type == "web_app" and button.action.web_app_url:
                                button_data["web_app"] = {"url": button.action.web_app_url}
                            elif button.action.type == "command" and button.action.command:
                                # For commands, we use callback data
                                button_data["callback_data"] = (
                                    TelegramPresentationRenderer._truncate_callback_data(
                                        f"cmd:{button.action.command}"
                                    )
                                )
                            elif button.action.type == "callback" and button.action.value:
                                button_data["callback_data"] = (
                                    TelegramPresentationRenderer._truncate_callback_data(
                                        button.action.value
                                    )
                                )
                        
                        if "callback_data" not in button_data and "url" not in button_data and "web_app" not in button_data:
                            # Fallback to callback data with label
                            button_data["callback_data"] = (
                                TelegramPresentationRenderer._truncate_callback_data(label)
                            )
                        
                        current_row.append(button_data)
                    
                    if current_row:
                        inline_keyboard.append(current_row)
            
            # Note: SELECT blocks are converted to BUTTONS by adapt_presentation()
            # before this loop runs (Telegram has supports_select=False), so no
            # separate SELECT branch is needed here.
        
        result = {"text": "\n\n".join(text_parts) if text_parts else "\u200B"}  # Zero-width space if no text
        
        if inline_keyboard:
            result["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        return result


class SlackPresentationRenderer:
    """Renders presentations as Slack blocks."""
    
    @staticmethod
    def get_limits() -> "PresentationLimits":
        """Get Slack-specific presentation limits."""
        from praisonaiagents.bots.presentation import PresentationLimits
        return PresentationLimits.slack()
    
    @staticmethod
    def render(presentation: "MessagePresentation") -> Dict[str, Any]:
        """Render a presentation for Slack.
        
        Args:
            presentation: The presentation to render
            
        Returns:
            Dict with 'blocks' for Slack Block Kit
        """
        from praisonaiagents.bots.presentation import (
            BlockType,
            PresentationLimits,
            adapt_presentation,
        )
        
        presentation = adapt_presentation(presentation, PresentationLimits.slack())
        
        blocks = []
        
        for block in presentation.blocks:
            if block.type == BlockType.TEXT or block.type == "text":
                if block.text:
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": block.text[:3000]
                        }
                    })
            
            elif block.type == BlockType.CONTEXT or block.type == "context":
                if block.text:
                    blocks.append({
                        "type": "context",
                        "elements": [{
                            "type": "mrkdwn",
                            "text": block.text[:3000]
                        }]
                    })
            
            elif block.type == BlockType.DIVIDER or block.type == "divider":
                blocks.append({"type": "divider"})
            
            elif block.type == BlockType.BUTTONS or block.type == "buttons":
                if block.buttons:
                    # Presentation is pre-adapted to Slack limits (priority-aware)
                    elements = []
                    for button in block.buttons:
                        button_element = {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": button.label
                            }
                        }
                        
                        # Handle action
                        if button.url:
                            button_element["url"] = button.url
                        elif button.action:
                            if button.action.type == "url" and button.action.url:
                                button_element["url"] = button.action.url
                            elif button.action.type == "command" and button.action.command:
                                button_element["value"] = button.action.command
                                button_element["action_id"] = f"cmd_{hash(button.action.command) % 10000}"
                            elif button.action.type == "callback" and button.action.value:
                                button_element["value"] = button.action.value
                                button_element["action_id"] = f"cb_{hash(button.action.value) % 10000}"
                        
                        # Handle style
                        if button.style == "primary":
                            button_element["style"] = "primary"
                        elif button.style == "danger":
                            button_element["style"] = "danger"
                        
                        elements.append(button_element)
                    
                    if elements:
                        blocks.append({
                            "type": "actions",
                            "elements": elements
                        })
            
            elif block.type == BlockType.SELECT or block.type == "select":
                if block.options:
                    options = []
                    for option in block.options[:100]:
                        opt = {
                            "text": {
                                "type": "plain_text",
                                "text": option.label[:75]
                            },
                            "value": option.value[:75]
                        }
                        if option.description:
                            opt["description"] = {
                                "type": "plain_text",
                                "text": option.description[:75]
                            }
                        options.append(opt)
                    
                    if options:
                        blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": block.placeholder or "Select an option"
                            },
                            "accessory": {
                                "type": "static_select",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": block.placeholder or "Select..."
                                },
                                "options": options,
                                "action_id": block.action_id or "select_1"
                            }
                        })
        
        return {"blocks": blocks}


class DiscordPresentationRenderer:
    """Renders presentations as Discord components."""
    
    @staticmethod
    def get_limits() -> "PresentationLimits":
        """Get Discord-specific presentation limits."""
        from praisonaiagents.bots.presentation import PresentationLimits
        return PresentationLimits.discord()
    
    @staticmethod
    def render(presentation: "MessagePresentation") -> Dict[str, Any]:
        """Render a presentation for Discord.
        
        Args:
            presentation: The presentation to render
            
        Returns:
            Dict with 'content' and optional 'components'
        """
        from praisonaiagents.bots.presentation import (
            BlockType,
            PresentationLimits,
            adapt_presentation,
        )
        
        presentation = adapt_presentation(presentation, PresentationLimits.discord())
        
        text_parts = []
        components = []
        
        for block in presentation.blocks:
            if block.type == BlockType.TEXT or block.type == "text":
                if block.text:
                    text_parts.append(block.text)
            
            elif block.type == BlockType.CONTEXT or block.type == "context":
                if block.text:
                    text_parts.append(f"*{block.text}*")
            
            elif block.type == BlockType.DIVIDER or block.type == "divider":
                text_parts.append("—" * 20)
            
            elif block.type == BlockType.BUTTONS or block.type == "buttons":
                if block.buttons:
                    # Discord allows up to 5 buttons per row, 5 rows max
                    action_rows = []
                    current_row = []
                    
                    for button in block.buttons:  # Pre-capped by adapt_presentation()
                        if len(current_row) >= 5:
                            action_rows.append({
                                "type": 1,  # ACTION_ROW
                                "components": current_row
                            })
                            current_row = []
                        
                        button_component = {
                            "type": 2,  # BUTTON
                            "label": button.label[:80]
                        }
                        
                        # Handle style
                        style_map = {
                            "primary": 1,
                            "secondary": 2,
                            "success": 3,
                            "danger": 4,
                        }
                        button_component["style"] = style_map.get(button.style, 2)
                        
                        # Handle action
                        if button.url:
                            button_component["style"] = 5  # LINK style
                            button_component["url"] = button.url
                        elif button.action:
                            if button.action.type == "url" and button.action.url:
                                button_component["style"] = 5
                                button_component["url"] = button.action.url
                            else:
                                # For commands and callbacks, use custom_id
                                if button.action.type == "command" and button.action.command:
                                    button_component["custom_id"] = f"cmd:{button.action.command[:80]}"
                                elif button.action.type == "callback" and button.action.value:
                                    button_component["custom_id"] = button.action.value[:100]
                        
                        if "custom_id" not in button_component and "url" not in button_component:
                            button_component["custom_id"] = f"btn_{hash(button.label) % 10000}"
                        
                        if button.disabled:
                            button_component["disabled"] = True
                        
                        current_row.append(button_component)
                    
                    if current_row:
                        action_rows.append({
                            "type": 1,
                            "components": current_row
                        })
                    
                    components.extend(action_rows)
            
            elif block.type == BlockType.SELECT or block.type == "select":
                if block.options:
                    select_menu = {
                        "type": 3,  # STRING_SELECT
                        "custom_id": block.action_id or f"select_{hash(str(block.options)) % 10000}",
                        "placeholder": block.placeholder or "Select an option",
                        "options": []
                    }
                    
                    for option in block.options[:25]:
                        opt = {
                            "label": option.label[:100],
                            "value": option.value[:100]
                        }
                        if option.description:
                            opt["description"] = option.description[:100]
                        if option.emoji:
                            opt["emoji"] = {"name": option.emoji}
                        if option.default:
                            opt["default"] = True
                        select_menu["options"].append(opt)
                    
                    components.append({
                        "type": 1,
                        "components": [select_menu]
                    })
        
        result = {"content": "\n\n".join(text_parts)[:2000] if text_parts else "\u200B"}
        
        if components:
            result["components"] = components[:5]  # Max 5 action rows
        
        if presentation.ephemeral:
            result["flags"] = 64  # EPHEMERAL flag
        
        return result


class WhatsAppPresentationRenderer:
    """Renders presentations as WhatsApp Cloud API interactive messages.

    WhatsApp natively supports two interactive shapes:

    * ``interactive.type == "button"`` — up to 3 tappable reply buttons.
    * ``interactive.type == "list"`` — a menu whose rows map to select
      options (up to 10). Used for ``select`` blocks and for button rows that
      overflow the 3-button reply limit.

    The returned payload is the ``interactive`` object (plus a ``body`` text)
    ready to nest under ``{"type": "interactive", "interactive": ...}``. When a
    presentation has no interactive block, a plain ``{"text": ...}`` payload is
    returned so callers can fall back to a text send.
    """

    # WhatsApp reply buttons: at most 3 per message.
    _MAX_REPLY_BUTTONS = 3
    # WhatsApp list rows: at most 10 across all sections.
    _MAX_LIST_ROWS = 10
    # Reply-button id / list-row id cap (Cloud API rejects ids > 256 chars).
    _MAX_ID_LEN = 256

    @staticmethod
    def get_limits() -> "PresentationLimits":
        """Get WhatsApp-specific presentation limits."""
        from praisonaiagents.bots.presentation import PresentationLimits
        return PresentationLimits.whatsapp()

    @staticmethod
    def _button_id(button: "PresentationButton") -> str:
        """Derive a stable reply id (callback/reply/command value) for a button."""
        action = button.action
        value: Optional[str] = None
        if action is not None:
            atype = action.type.value if hasattr(action.type, "value") else action.type
            if atype == "command" and action.command:
                value = f"cmd:{action.command}"
            elif action.value:
                value = action.value
            elif action.url:
                value = action.url
        if not value:
            value = button.label
        return value[: WhatsAppPresentationRenderer._MAX_ID_LEN]

    @staticmethod
    def render(presentation: "MessagePresentation") -> Dict[str, Any]:
        """Render a presentation for WhatsApp Cloud API.

        Returns one of:
        * ``{"text": <str>}`` — no interactive content.
        * ``{"text": <body>, "interactive": {...}}`` — a native interactive
          message (button or list), where ``interactive`` is the Cloud API
          ``interactive`` object.
        """
        from praisonaiagents.bots.presentation import (
            BlockType,
            PresentationLimits,
            adapt_presentation,
        )

        presentation = adapt_presentation(presentation, PresentationLimits.whatsapp())

        text_parts: List[str] = []
        buttons: List["PresentationButton"] = []
        select_block: Optional["PresentationBlock"] = None

        for block in presentation.blocks:
            btype = block.type.value if hasattr(block.type, "value") else block.type
            if btype in (BlockType.TEXT, "text"):
                if block.text:
                    text_parts.append(block.text)
            elif btype in (BlockType.CONTEXT, "context"):
                if block.text:
                    text_parts.append(block.text)
            elif btype in (BlockType.DIVIDER, "divider"):
                text_parts.append("—" * 20)
            elif btype in (BlockType.BUTTONS, "buttons"):
                if block.buttons:
                    buttons.extend(block.buttons)
            elif btype in (BlockType.SELECT, "select"):
                # adapt_presentation keeps selects for WhatsApp (supports_select
                # is True); render the first select as a list message.
                if block.options and select_block is None:
                    select_block = block

        body = "\n\n".join(p for p in text_parts if p) or "\u200b"
        body = body[:1024]  # WhatsApp interactive body cap

        # Link buttons (url actions) cannot be reply buttons; keep them as text
        # links appended to the body so the URL is still reachable.
        url_lines: List[str] = []

        def _is_url_button(btn: "PresentationButton") -> bool:
            if btn.url:
                return True
            action = btn.action
            if action is not None:
                atype = action.type.value if hasattr(action.type, "value") else action.type
                return atype == "url" and bool(action.url)
            return False

        tappable = [b for b in buttons if not _is_url_button(b)]
        for b in buttons:
            if _is_url_button(b):
                link = b.url or (b.action.url if b.action else None)
                if link:
                    url_lines.append(f"{b.label}: {link}")

        # Prefer a native select list; otherwise map buttons to button/list.
        if select_block is not None and select_block.options:
            rows = []
            for option in select_block.options[: WhatsAppPresentationRenderer._MAX_LIST_ROWS]:
                row = {
                    "id": (option.value or option.label)[: WhatsAppPresentationRenderer._MAX_ID_LEN],
                    "title": option.label[:24],
                }
                if option.description:
                    row["description"] = option.description[:72]
                rows.append(row)
            interactive = {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": (select_block.placeholder or "Select")[:20],
                    "sections": [{"title": "Options", "rows": rows}],
                },
            }
            result: Dict[str, Any] = {"text": body, "interactive": interactive}
            if url_lines:
                result["interactive"]["footer"] = {"text": "\n".join(url_lines)[:60]}
            return result

        if tappable:
            if len(tappable) <= WhatsAppPresentationRenderer._MAX_REPLY_BUTTONS:
                reply_buttons = [
                    {
                        "type": "reply",
                        "reply": {
                            "id": WhatsAppPresentationRenderer._button_id(b),
                            "title": b.label[:20],
                        },
                    }
                    for b in tappable
                ]
                interactive = {
                    "type": "button",
                    "body": {"text": body},
                    "action": {"buttons": reply_buttons},
                }
            else:
                # Overflow: promote reply buttons into a list message.
                rows = []
                for b in tappable[: WhatsAppPresentationRenderer._MAX_LIST_ROWS]:
                    rows.append({
                        "id": WhatsAppPresentationRenderer._button_id(b),
                        "title": b.label[:24],
                    })
                interactive = {
                    "type": "list",
                    "body": {"text": body},
                    "action": {
                        "button": "Choose",
                        "sections": [{"title": "Options", "rows": rows}],
                    },
                }
            result = {"text": body, "interactive": interactive}
            if url_lines:
                result["interactive"]["footer"] = {"text": "\n".join(url_lines)[:60]}
            return result

        # No interactive content: plain text (append any url links).
        if url_lines:
            body = (body + "\n\n" + "\n".join(url_lines))[:4096]
        return {"text": body}


# Registry keyed by platform id so adapters resolve their renderer uniformly.
# New channels plug in by adding an entry here; adapters call ``render_for``.
_RENDERERS: Dict[str, type] = {
    "telegram": TelegramPresentationRenderer,
    "slack": SlackPresentationRenderer,
    "discord": DiscordPresentationRenderer,
    "whatsapp": WhatsAppPresentationRenderer,
}


def get_renderer(platform: str) -> Optional[type]:
    """Return the registered renderer class for *platform*, or ``None``."""
    return _RENDERERS.get(platform)


def fallback_text(presentation: "MessagePresentation") -> Dict[str, Any]:
    """Flatten a presentation to a plain-text payload for channels without a
    native renderer.

    Text/context/divider blocks become lines; buttons and select options are
    listed as readable text (with any URLs inlined) so the content is never
    silently dropped.
    """
    from praisonaiagents.bots.presentation import BlockType

    lines: List[str] = []
    for block in presentation.blocks:
        btype = block.type.value if hasattr(block.type, "value") else block.type
        if btype in (BlockType.TEXT, "text", BlockType.CONTEXT, "context"):
            if block.text:
                lines.append(block.text)
        elif btype in (BlockType.DIVIDER, "divider"):
            lines.append("—" * 20)
        elif btype in (BlockType.BUTTONS, "buttons"):
            for b in (block.buttons or []):
                url = b.url or (b.action.url if b.action else None)
                lines.append(f"• {b.label}" + (f": {url}" if url else ""))
        elif btype in (BlockType.SELECT, "select"):
            for o in (block.options or []):
                lines.append(f"• {o.label}")
    return {"text": "\n".join(lines) if lines else "\u200b"}


def render_for(platform: str, presentation: "MessagePresentation") -> Dict[str, Any]:
    """Render *presentation* for *platform* through the renderer registry.

    Resolves the platform's registered :class:`PresentationRenderer` and
    returns its native payload. Channels with no registered renderer fall back
    to :func:`fallback_text` so interactive content still degrades gracefully
    to readable plain text rather than being dropped.
    """
    renderer = _RENDERERS.get(platform)
    if renderer is not None:
        return renderer.render(presentation)
    return fallback_text(presentation)