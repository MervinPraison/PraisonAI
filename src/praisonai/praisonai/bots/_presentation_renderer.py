"""
Presentation rendering implementations for messaging platforms.

Converts portable MessagePresentation objects into platform-specific
interactive UI components (Telegram inline keyboards, Slack blocks, etc).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

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


class TelegramPresentationRenderer:
    """Renders presentations as Telegram inline keyboards."""
    
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
                                button_data["callback_data"] = f"cmd:{button.action.command}"[:64]
                            elif button.action.type == "callback" and button.action.value:
                                button_data["callback_data"] = button.action.value[:64]
                        
                        if "callback_data" not in button_data and "url" not in button_data and "web_app" not in button_data:
                            # Fallback to callback data with label
                            button_data["callback_data"] = label[:64]
                        
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