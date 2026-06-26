"""
Presentation primitives for interactive UI in messaging bots.

Defines typed, portable presentation blocks (buttons, selects, text)
that channel adapters render as native widgets. Enables structured
interactive UI across Telegram, Slack, Discord, and other platforms.

This is a core protocol with no heavy implementations - channel-specific
rendering belongs in the wrapper (praisonai).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

# Most channels (e.g. Telegram) hard-cap inline callback payloads at 64 bytes.
# Keep degraded select callbacks within this bound while preserving uniqueness.
_MAX_CALLBACK_LEN = 64


class ActionType(str, Enum):
    """Types of actions that can be triggered by interactive elements."""
    
    COMMAND = "command"      # Execute a slash command
    CALLBACK = "callback"     # Opaque callback data for the plugin
    URL = "url"              # Open a URL
    WEB_APP = "web_app"      # Open a web app (Telegram mini apps, etc)
    REPLY = "reply"          # Feed value back into the agent turn as next input


class ButtonStyle(str, Enum):
    """Visual styles for buttons."""
    
    PRIMARY = "primary"      # Primary action (blue/green)
    DANGER = "danger"        # Destructive action (red)
    SECONDARY = "secondary"  # Secondary action (gray)
    SUCCESS = "success"      # Success action (green)
    WARNING = "warning"      # Warning action (yellow)


class BlockType(str, Enum):
    """Types of presentation blocks."""
    
    TEXT = "text"            # Text content
    BUTTONS = "buttons"      # Button row/grid
    SELECT = "select"        # Dropdown/select menu
    DIVIDER = "divider"      # Visual separator
    CONTEXT = "context"      # Contextual info (smaller text)


@dataclass
class PresentationAction:
    """An action triggered by an interactive element.
    
    Attributes:
        type: The action type (command, callback, url, web_app)
        command: Slash command to execute (for type="command")
        value: Callback data (for type="callback")
        url: URL to open (for type="url")
        web_app_url: Web app URL (for type="web_app")
    """
    
    type: Union[ActionType, str]
    command: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    web_app_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {"type": self.type.value if isinstance(self.type, ActionType) else self.type}
        if self.command is not None:
            data["command"] = self.command
        if self.value is not None:
            data["value"] = self.value
        if self.url is not None:
            data["url"] = self.url
        if self.web_app_url is not None:
            data["web_app_url"] = self.web_app_url
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresentationAction":
        """Create from dictionary."""
        return cls(
            type=data.get("type", "callback"),
            command=data.get("command"),
            value=data.get("value"),
            url=data.get("url"),
            web_app_url=data.get("web_app_url"),
        )

    @classmethod
    def reply(cls, value: str) -> "PresentationAction":
        """Create a ``reply`` action that feeds *value* back into the agent turn.

        When a user clicks a button (or picks a select option) carrying a reply
        action, the chosen *value* is routed back through the interactive
        registry as the next agent input — no ``/``-prefixed command parsing by
        channels required. See ``ActionType.REPLY`` and the ``reply`` namespace
        handler in ``interactive.py``.
        """
        return cls(type=ActionType.REPLY, value=value)

    @classmethod
    def callback(cls, value: str) -> "PresentationAction":
        """Create an opaque ``callback`` action carrying *value*."""
        return cls(type=ActionType.CALLBACK, value=value)

    @classmethod
    def command(cls, command: str) -> "PresentationAction":
        """Create a ``command`` action that runs a slash *command*."""
        return cls(type=ActionType.COMMAND, command=command)

    @classmethod
    def open_url(cls, url: str) -> "PresentationAction":
        """Create a ``url`` action that opens *url*."""
        return cls(type=ActionType.URL, url=url)


@dataclass
class PresentationButton:
    """A button in an interactive presentation.
    
    Attributes:
        label: Button text label
        action: Action to trigger when clicked
        url: Direct URL (alternative to action)
        priority: Truncation priority (higher survives)
        style: Visual style
        disabled: Whether button is disabled
    """
    
    label: str
    action: Optional[PresentationAction] = None
    url: Optional[str] = None
    priority: int = 0
    style: Optional[Union[ButtonStyle, str]] = None
    disabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {"label": self.label, "priority": self.priority, "disabled": self.disabled}
        if self.action is not None:
            data["action"] = self.action.to_dict()
        if self.url is not None:
            data["url"] = self.url
        if self.style is not None:
            data["style"] = self.style.value if isinstance(self.style, ButtonStyle) else self.style
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresentationButton":
        """Create from dictionary."""
        return cls(
            label=data.get("label", ""),
            action=PresentationAction.from_dict(data["action"]) if "action" in data else None,
            url=data.get("url"),
            priority=data.get("priority", 0),
            style=data.get("style"),
            disabled=data.get("disabled", False),
        )


@dataclass
class SelectOption:
    """An option in a select menu.
    
    Attributes:
        label: Option text label
        value: Option value
        description: Optional description
        emoji: Optional emoji icon
        default: Whether this is the default option
    """
    
    label: str
    value: str
    description: Optional[str] = None
    emoji: Optional[str] = None
    default: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {"label": self.label, "value": self.value, "default": self.default}
        if self.description is not None:
            data["description"] = self.description
        if self.emoji is not None:
            data["emoji"] = self.emoji
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelectOption":
        """Create from dictionary."""
        return cls(
            label=data.get("label", ""),
            value=data.get("value", ""),
            description=data.get("description"),
            emoji=data.get("emoji"),
            default=data.get("default", False),
        )


@dataclass
class PresentationBlock:
    """A block in a message presentation.
    
    Blocks are the building blocks of interactive messages.
    Each block type has specific properties and behavior.
    """
    
    type: Union[BlockType, str]
    text: Optional[str] = None
    buttons: Optional[List[PresentationButton]] = None
    options: Optional[List[SelectOption]] = None
    placeholder: Optional[str] = None
    action_id: Optional[str] = None
    
    @staticmethod
    def make_text(content: str, markdown: bool = True) -> "PresentationBlock":
        """Create a text block."""
        return PresentationBlock(type=BlockType.TEXT, text=content)
    
    @staticmethod
    def make_buttons(items: List[PresentationButton]) -> "PresentationBlock":
        """Create a buttons block."""
        return PresentationBlock(type=BlockType.BUTTONS, buttons=items)
    
    @staticmethod
    def make_select(
        options: List[SelectOption],
        placeholder: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> "PresentationBlock":
        """Create a select menu block."""
        return PresentationBlock(
            type=BlockType.SELECT,
            options=options,
            placeholder=placeholder,
            action_id=action_id,
        )
    
    @staticmethod
    def make_divider() -> "PresentationBlock":
        """Create a divider block."""
        return PresentationBlock(type=BlockType.DIVIDER)
    
    @staticmethod
    def make_context(content: str) -> "PresentationBlock":
        """Create a context block (smaller text)."""
        return PresentationBlock(type=BlockType.CONTEXT, text=content)

    @staticmethod
    def quick_replies(
        choices: List[Any],
        priority_base: int = 0,
    ) -> "PresentationBlock":
        """Create a row of quick-reply buttons from ``(label, value)`` pairs.

        Each choice may be a ``(label, value)`` tuple or a plain string (used as
        both label and value). Every button carries a ``reply`` action so a
        click feeds ``value`` back into the next agent turn. This is the
        agent-facing shortcut for the common "pick one" interaction.
        """
        items: List["PresentationButton"] = []
        for choice in choices:
            if isinstance(choice, (tuple, list)) and len(choice) >= 2:
                label, value = choice[0], choice[1]
            else:
                label = value = choice
            items.append(
                PresentationButton(
                    label=str(label),
                    action=PresentationAction.reply(str(value)),
                    priority=priority_base,
                )
            )
        return PresentationBlock(type=BlockType.BUTTONS, buttons=items)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {"type": self.type.value if isinstance(self.type, BlockType) else self.type}
        if self.text is not None:
            data["text"] = self.text
        if self.buttons is not None:
            data["buttons"] = [b.to_dict() for b in self.buttons]
        if self.options is not None:
            data["options"] = [o.to_dict() for o in self.options]
        if self.placeholder is not None:
            data["placeholder"] = self.placeholder
        if self.action_id is not None:
            data["action_id"] = self.action_id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresentationBlock":
        """Create from dictionary."""
        return cls(
            type=data.get("type", "text"),
            text=data.get("text"),
            buttons=(
                [PresentationButton.from_dict(b) for b in data["buttons"]]
                if "buttons" in data else None
            ),
            options=(
                [SelectOption.from_dict(o) for o in data["options"]]
                if "options" in data else None
            ),
            placeholder=data.get("placeholder"),
            action_id=data.get("action_id"),
        )


@dataclass
class MessagePresentation:
    """A complete interactive message presentation.
    
    Attributes:
        blocks: List of presentation blocks
        tone: Optional tone/style hint for the whole message
        ephemeral: Whether message should be ephemeral/temporary
        replace_message_id: ID of message to replace (for updates)
    """
    
    blocks: List[PresentationBlock] = field(default_factory=list)
    tone: Optional[str] = None
    ephemeral: bool = False
    replace_message_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {"blocks": [b.to_dict() for b in self.blocks], "ephemeral": self.ephemeral}
        if self.tone is not None:
            data["tone"] = self.tone
        if self.replace_message_id is not None:
            data["replace_message_id"] = self.replace_message_id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessagePresentation":
        """Create from dictionary."""
        return cls(
            blocks=[PresentationBlock.from_dict(b) for b in data.get("blocks", [])],
            tone=data.get("tone"),
            ephemeral=data.get("ephemeral", False),
            replace_message_id=data.get("replace_message_id"),
        )
    
    @staticmethod
    def approval(
        prompt: str,
        approval_id: str,
        allow_always: bool = False,
        context: Optional[str] = None,
    ) -> "MessagePresentation":
        """Create a standard approval presentation.
        
        Args:
            prompt: The approval prompt text
            approval_id: Unique ID for this approval
            allow_always: Whether to include "Allow Always" option
            context: Optional context information
            
        Returns:
            A presentation with standard approval buttons
        """
        blocks = []
        
        # Add prompt
        blocks.append(PresentationBlock.make_text(prompt))
        
        # Add context if provided
        if context:
            blocks.append(PresentationBlock.make_context(context))
        
        # Create buttons
        buttons = [
            PresentationButton(
                label="Allow Once",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} allow-once"
                ),
                style=ButtonStyle.PRIMARY,
                priority=10,
            ),
            PresentationButton(
                label="Deny",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} deny"
                ),
                style=ButtonStyle.DANGER,
                priority=9,
            ),
        ]
        
        if allow_always:
            buttons.insert(1, PresentationButton(
                label="Allow Always",
                action=PresentationAction(
                    type=ActionType.COMMAND,
                    command=f"/approve {approval_id} allow-always"
                ),
                style=ButtonStyle.SUCCESS,
                priority=8,
            ))
        
        blocks.append(PresentationBlock.make_buttons(buttons))
        
        return MessagePresentation(blocks=blocks)


@dataclass
class PresentationLimits:
    """Channel-specific limits for presentations.
    
    Attributes:
        max_buttons: Maximum buttons per row/message
        max_button_rows: Maximum button rows
        max_button_label: Maximum characters in button label
        max_options: Maximum options in select menu
        max_option_label: Maximum characters in option label
        max_text_length: Maximum text block length
        supports_markdown: Whether channel supports markdown
        supports_select: Whether channel supports select menus
        supports_web_apps: Whether channel supports web apps
    """
    
    max_buttons: int = 10
    max_button_rows: int = 5
    max_button_label: int = 50
    max_options: int = 25
    max_option_label: int = 50
    max_text_length: int = 4096
    supports_markdown: bool = True
    supports_select: bool = True
    supports_web_apps: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_buttons": self.max_buttons,
            "max_button_rows": self.max_button_rows,
            "max_button_label": self.max_button_label,
            "max_options": self.max_options,
            "max_option_label": self.max_option_label,
            "max_text_length": self.max_text_length,
            "supports_markdown": self.supports_markdown,
            "supports_select": self.supports_select,
            "supports_web_apps": self.supports_web_apps,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresentationLimits":
        """Create from dictionary."""
        return cls(
            max_buttons=data.get("max_buttons", 10),
            max_button_rows=data.get("max_button_rows", 5),
            max_button_label=data.get("max_button_label", 50),
            max_options=data.get("max_options", 25),
            max_option_label=data.get("max_option_label", 50),
            max_text_length=data.get("max_text_length", 4096),
            supports_markdown=data.get("supports_markdown", True),
            supports_select=data.get("supports_select", True),
            supports_web_apps=data.get("supports_web_apps", False),
        )
    
    @staticmethod
    def telegram() -> "PresentationLimits":
        """Get Telegram-specific limits."""
        return PresentationLimits(
            max_buttons=8,
            max_button_rows=100,
            max_button_label=64,
            max_options=0,  # No native select
            max_text_length=4096,
            supports_markdown=True,
            supports_select=False,
            supports_web_apps=True,
        )
    
    @staticmethod
    def slack() -> "PresentationLimits":
        """Get Slack-specific limits."""
        return PresentationLimits(
            max_buttons=5,
            max_button_rows=1,
            max_button_label=75,
            max_options=100,
            max_option_label=75,
            max_text_length=3000,
            supports_markdown=True,
            supports_select=True,
            supports_web_apps=False,
        )
    
    @staticmethod
    def discord() -> "PresentationLimits":
        """Get Discord-specific limits."""
        return PresentationLimits(
            max_buttons=5,  # per-row capacity; total cap = max_buttons * max_button_rows = 25
            max_button_rows=5,
            max_button_label=80,
            max_options=25,
            max_option_label=100,
            max_text_length=2000,
            supports_markdown=True,
            supports_select=True,
            supports_web_apps=False,
        )


def _adapt_button(button: PresentationButton, limits: PresentationLimits) -> PresentationButton:
    """Return a copy of a button adapted to the given limits.

    Truncates the label and, when the channel does not support web apps,
    degrades a ``web_app`` action to a plain URL so the button still works.
    """
    label = button.label or ""
    if limits.max_button_label and len(label) > limits.max_button_label:
        label = label[: limits.max_button_label]

    action = button.action
    url = button.url
    if action is not None:
        action_type = action.type.value if isinstance(action.type, ActionType) else action.type
        # Degrade reply -> callback so existing per-channel renderers (which only
        # map command/callback/url/web_app) can carry the payload. The
        # ``reply:`` prefix lets the inbound registry route the chosen value
        # back into the next agent turn (see interactive.py).
        if action_type == ActionType.REPLY.value and action.value is not None:
            action = PresentationAction(
                type=ActionType.CALLBACK,
                value=_encode_reply_callback(action.value),
            )
        elif (
            not limits.supports_web_apps
            and action_type == ActionType.WEB_APP.value
            and action.web_app_url
        ):
            # Degrade web_app -> url when unsupported
            if url is None:
                url = action.web_app_url
            action = PresentationAction(type=ActionType.URL, url=action.web_app_url)

    return PresentationButton(
        label=label,
        action=action,
        url=url,
        priority=button.priority,
        style=button.style,
        disabled=button.disabled,
    )


REPLY_CALLBACK_PREFIX = "reply:"


def _truncate_utf8(value: str, max_bytes: int) -> str:
    """Truncate *value* so its UTF-8 encoding fits within *max_bytes*.

    Trims on a character boundary (never splitting a multi-byte codepoint) so
    the result stays a valid, decodable string.
    """
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    truncated = encoded[:max_bytes]
    # Drop any trailing partial multi-byte sequence.
    return truncated.decode("utf-8", "ignore")


def _encode_reply_callback(value: str) -> str:
    """Build a channel-safe callback payload for a ``reply`` action.

    Produces ``reply:<value>`` so the inbound interactive registry can route
    the chosen value back into the next agent turn. The size check is measured
    in UTF-8 bytes because channel callback caps (e.g. Telegram's 64-byte cap)
    are byte limits, not character limits. When the raw form exceeds
    ``_MAX_CALLBACK_LEN`` the value is truncated to fit (on a character
    boundary) so the routed value stays human/agent-readable rather than an
    opaque digest the next turn cannot interpret.
    """
    raw = f"{REPLY_CALLBACK_PREFIX}{value}"
    if len(raw.encode("utf-8")) <= _MAX_CALLBACK_LEN:
        return raw
    budget = _MAX_CALLBACK_LEN - len(REPLY_CALLBACK_PREFIX.encode("utf-8"))
    return f"{REPLY_CALLBACK_PREFIX}{_truncate_utf8(value, budget)}"


def _encode_select_callback(action_id: str, value: str) -> str:
    """Build a channel-safe callback payload for a degraded select option.

    The raw ``select:<action_id>:<value>`` form can exceed channel callback
    limits (e.g. Telegram's 64-byte cap) and collide when distinct options
    share a long prefix. When the raw payload fits within ``_MAX_CALLBACK_LEN``
    it is returned unchanged; otherwise the value is replaced with a short,
    collision-resistant hash so distinct options stay distinct after truncation.
    """
    raw = f"select:{action_id}:{value}"
    if len(raw.encode("utf-8")) <= _MAX_CALLBACK_LEN:
        return raw
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    prefix = f"select:{action_id}:"
    # Reserve room for the digest; trim the action_id prefix if needed.
    budget = _MAX_CALLBACK_LEN - len(digest)
    if budget < len("select::"):
        # action_id itself is too long; hash it too to guarantee the bound.
        aid_digest = hashlib.sha1((action_id or "").encode("utf-8")).hexdigest()[:8]
        prefix = f"select:{aid_digest}:"
    return f"{prefix[:_MAX_CALLBACK_LEN - len(digest)]}{digest}"


def _select_to_buttons(block: PresentationBlock) -> PresentationBlock:
    """Convert a SELECT block into an equivalent BUTTONS block.

    Used when a channel does not support native select menus. Each option
    becomes a callback button carrying a bounded, channel-safe identifier
    derived from ``select:<action_id>:<value>``.
    """
    buttons: List[PresentationButton] = []
    action_id = block.action_id or ""
    for option in (block.options or []):
        label = option.label
        if option.emoji:
            label = f"{option.emoji} {label}"
        buttons.append(
            PresentationButton(
                label=label,
                action=PresentationAction(
                    type=ActionType.CALLBACK,
                    value=_encode_select_callback(action_id, option.value),
                ),
            )
        )
    return PresentationBlock(type=BlockType.BUTTONS, buttons=buttons)


def adapt_presentation(
    presentation: MessagePresentation,
    limits: PresentationLimits,
) -> MessagePresentation:
    """Return a copy of ``presentation`` guaranteed to satisfy ``limits``.

    This is the single, channel-agnostic adaptation pass that channel
    renderers should run before mapping a presentation to native widgets.
    It performs:

    1. Priority-aware button truncation: when a buttons block exceeds
       ``max_buttons`` (or the implied ``max_buttons * max_button_rows``
       cap), the lowest-``priority`` buttons are dropped first (highest
       survives), preserving original order among kept buttons.
    2. Label truncation to ``max_button_label`` / ``max_option_label``.
    3. Option truncation to ``max_options``.
    4. Capability degradation: ``select`` blocks become button rows when
       ``supports_select`` is False; ``web_app`` actions become URLs when
       ``supports_web_apps`` is False.

    The input presentation is never mutated.

    Args:
        presentation: The portable presentation to adapt.
        limits: The target channel's capability limits.

    Returns:
        A new ``MessagePresentation`` that is safe to render natively.
    """
    adapted_blocks: List[PresentationBlock] = []

    for block in presentation.blocks:
        block_type = block.type.value if isinstance(block.type, BlockType) else block.type

        if block_type == BlockType.SELECT.value and not limits.supports_select:
            # Degrade select -> buttons, then adapt the resulting buttons block
            block = _select_to_buttons(block)
            block_type = BlockType.BUTTONS.value

        if block_type == BlockType.BUTTONS.value and block.buttons:
            # Cap total buttons by max_buttons * max_button_rows (interpreting
            # max_buttons as per-row capacity), falling back to max_buttons.
            rows = limits.max_button_rows if limits.max_button_rows else 1
            total_cap = limits.max_buttons * rows if limits.max_buttons else len(block.buttons)
            if total_cap <= 0:
                total_cap = len(block.buttons)

            buttons = list(block.buttons)
            if len(buttons) > total_cap:
                # Keep highest-priority buttons; preserve original order among kept.
                indexed = list(enumerate(buttons))
                kept = sorted(
                    indexed,
                    key=lambda iv: (iv[1].priority, -iv[0]),
                    reverse=True,
                )[:total_cap]
                kept.sort(key=lambda iv: iv[0])
                buttons = [b for _, b in kept]

            adapted_buttons = [_adapt_button(b, limits) for b in buttons]
            adapted_blocks.append(
                PresentationBlock(type=BlockType.BUTTONS, buttons=adapted_buttons)
            )
            continue

        if block_type == BlockType.SELECT.value and block.options:
            options = block.options
            if limits.max_options and len(options) > limits.max_options:
                options = options[: limits.max_options]
            new_options: List[SelectOption] = []
            for option in options:
                label = option.label
                if limits.max_option_label and len(label) > limits.max_option_label:
                    label = label[: limits.max_option_label]
                new_options.append(
                    SelectOption(
                        label=label,
                        value=option.value,
                        description=option.description,
                        emoji=option.emoji,
                        default=option.default,
                    )
                )
            adapted_blocks.append(
                PresentationBlock(
                    type=BlockType.SELECT,
                    options=new_options,
                    placeholder=block.placeholder,
                    action_id=block.action_id,
                )
            )
            continue

        if block_type == BlockType.TEXT.value or block_type == BlockType.CONTEXT.value:
            text = block.text
            if text is not None and limits.max_text_length and len(text) > limits.max_text_length:
                text = text[: limits.max_text_length]
            adapted_blocks.append(
                PresentationBlock(type=block.type, text=text)
            )
            continue

        adapted_blocks.append(block)

    return MessagePresentation(
        blocks=adapted_blocks,
        tone=presentation.tone,
        ephemeral=presentation.ephemeral,
        replace_message_id=presentation.replace_message_id,
    )


