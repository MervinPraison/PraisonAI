"""
Presentation primitives for interactive UI in messaging bots.

Defines typed, portable presentation blocks (buttons, selects, text)
that channel adapters render as native widgets. Enables structured
interactive UI across Telegram, Slack, Discord, and other platforms.

This is a core protocol with no heavy implementations - channel-specific
rendering belongs in ``praisonai-bot`` (``praisonai_bot.bots``).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
)

if TYPE_CHECKING:
    from .protocols import CallbackPayloadStoreProtocol

# Most channels (e.g. Telegram) hard-cap inline callback payloads at 64 bytes.
# Keep degraded select callbacks within this bound while preserving uniqueness.
_MAX_CALLBACK_LEN = 64

# Marker prefixing a stored-reference payload. When an interactive value does
# not fit the channel callback byte-cap and a ``CallbackPayloadStoreProtocol``
# is available, the canonical value is persisted under a short reference and the
# callback carries ``@<ref>`` instead of the (unrecoverable) hash. The inbound
# registry resolves the reference back to the exact value on click.
CALLBACK_REF_MARKER = "@"

# Default lifetime (seconds) for a persisted callback reference. An interactive
# menu is a short-lived affordance; a bounded TTL keeps the store from growing
# without cleanup while comfortably covering a user pondering their choice.
CALLBACK_REF_TTL = 3600.0


def _callback_ref(namespace: str, value: str) -> str:
    """Build a short, collision-resistant reference for a callback ``value``.

    The reference is derived from both the namespace/action scope and the value
    so distinct choices stay distinct, and is short enough to always fit within
    ``_MAX_CALLBACK_LEN`` alongside its prefix.
    """
    digest = hashlib.sha256(f"{namespace}\x00{value}".encode("utf-8")).hexdigest()
    return digest[:16]


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
    TABLE = "table"          # Tabular data (columns + rows)
    CHART = "chart"          # Chart/visualisation (kind + series)


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
    # Tabular data (TABLE blocks)
    columns: Optional[List[str]] = None
    rows: Optional[List[List[str]]] = None
    # Chart data (CHART blocks)
    chart_kind: Optional[str] = None
    series: Optional[List[Dict[str, Any]]] = None
    
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
    def make_table(
        columns: List[str],
        rows: List[List[str]],
    ) -> "PresentationBlock":
        """Create a table block from *columns* and *rows*.

        Describe tabular data once; channels with a native table widget render
        it directly, and everywhere else it degrades to a deterministic
        markdown table (see :func:`adapt_presentation`).
        """
        return PresentationBlock(
            type=BlockType.TABLE,
            columns=[str(c) for c in columns],
            rows=[[str(c) for c in row] for row in rows],
        )

    @staticmethod
    def make_chart(
        chart_kind: str,
        series: List[Dict[str, Any]],
        text: Optional[str] = None,
    ) -> "PresentationBlock":
        """Create a chart block.

        Args:
            chart_kind: One of ``"bar"``, ``"line"``, ``"pie"``, ``"area"``.
            series: A list of ``{"label": str, "points": list[float]}`` dicts.
            text: Optional caption/title for the chart.

        Channels with native visualisation render the series directly; elsewhere
        the chart degrades to a compact text summary (see
        :func:`adapt_presentation`).
        """
        return PresentationBlock(
            type=BlockType.CHART,
            chart_kind=chart_kind,
            series=series,
            text=text,
        )

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
        if self.columns is not None:
            data["columns"] = self.columns
        if self.rows is not None:
            data["rows"] = self.rows
        if self.chart_kind is not None:
            data["chart_kind"] = self.chart_kind
        if self.series is not None:
            data["series"] = self.series
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
            columns=data.get("columns"),
            rows=data.get("rows"),
            chart_kind=data.get("chart_kind"),
            series=data.get("series"),
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

    @staticmethod
    def question(
        prompt: str,
        options: List[Any],
        context: Optional[str] = None,
    ) -> "MessagePresentation":
        """Create a structured question presentation with option buttons.

        The symmetric counterpart to :meth:`approval` for non-binary
        clarifications ("which of these?"). Each option renders as a typed
        ``reply``-action button (via :meth:`PresentationBlock.quick_replies`),
        so a tap feeds the chosen value straight back into the next agent turn
        across any channel, reusing the existing reply routing and byte-safe
        callback encoding — no new store, protocol, or correlation machinery.

        Args:
            prompt: The question text.
            options: Choices as ``(label, value)`` pairs or plain strings.
            context: Optional context information rendered under the prompt.

        Returns:
            A presentation with the prompt and one reply button per option.
        """
        blocks = [PresentationBlock.make_text(prompt)]
        if context:
            blocks.append(PresentationBlock.make_context(context))
        blocks.append(PresentationBlock.quick_replies(options))
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
        supports_tables: Whether channel has a native table widget
        supports_charts: Whether channel has native chart/visualisation
        max_table_rows: Maximum rows in a table block
        max_table_cols: Maximum columns in a table block
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
    supports_tables: bool = False
    supports_charts: bool = False
    max_table_rows: int = 50
    max_table_cols: int = 10
    
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
            "supports_tables": self.supports_tables,
            "supports_charts": self.supports_charts,
            "max_table_rows": self.max_table_rows,
            "max_table_cols": self.max_table_cols,
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
            supports_tables=data.get("supports_tables", False),
            supports_charts=data.get("supports_charts", False),
            max_table_rows=data.get("max_table_rows", 50),
            max_table_cols=data.get("max_table_cols", 10),
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

    @staticmethod
    def whatsapp() -> "PresentationLimits":
        """Get WhatsApp Cloud API-specific limits.

        WhatsApp interactive messages support two native shapes:

        * *reply buttons* — at most 3 buttons, each label capped at 20 chars.
        * *list messages* — a single "menu" whose rows map naturally to select
          options (up to 10 rows), each row title capped at 24 chars.

        ``supports_select`` is True because a native list message renders a
        ``select`` block directly, and the WhatsApp renderer promotes button
        overflow (>3) into a list message as well. WhatsApp has no markdown and
        no web-app buttons, so those degrade via ``adapt_presentation``.
        """
        return PresentationLimits(
            max_buttons=10,  # list-message row cap; ≤3 render as reply buttons
            max_button_rows=1,
            max_button_label=24,  # list-row title hard cap; renderer caps reply buttons at 20
            max_options=10,  # list-message rows
            max_option_label=24,  # list-row title hard cap
            max_text_length=4096,
            supports_markdown=False,
            supports_select=True,
            supports_web_apps=False,
        )


def _adapt_button(
    button: PresentationButton,
    limits: PresentationLimits,
    store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> PresentationButton:
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
                value=_encode_reply_callback(action.value, store),
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

# Marker prefixing a hashed (non-routable) reply payload. A reply value that
# does not fit the channel callback byte-cap is encoded as
# ``reply:#<digest>``. The ``#`` marker lets the inbound reply handler detect a
# lossy payload and refuse to feed a corrupted/colliding value into the next
# agent turn (see ``make_reply_handler``), rather than silently routing a
# truncated prefix that two distinct choices could share.
REPLY_HASH_MARKER = "#"


def _encode_reply_callback(
    value: str,
    store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> str:
    """Build a channel-safe callback payload for a ``reply`` action.

    Produces ``reply:<value>`` so the inbound interactive registry can route
    the chosen value back into the next agent turn. The size check is measured
    in UTF-8 bytes because channel callback caps (e.g. Telegram's 64-byte cap)
    are byte limits, not character limits.

    When the raw form exceeds ``_MAX_CALLBACK_LEN`` and a *store* is available,
    the canonical value is persisted under a short reference and the callback
    carries ``reply:@<ref>``; the inbound handler resolves the reference back to
    the exact value, so long values round-trip losslessly.

    Without a store the value is replaced with a short, collision-resistant hash
    marked with ``#`` (``reply:#<digest>``). Truncating to a prefix was unsafe:
    two long choices sharing a prefix would collapse to the same payload. The
    marker lets the reply handler recognise that the original value could not be
    carried and avoid routing a lossy value into the turn.
    """
    raw = f"{REPLY_CALLBACK_PREFIX}{value}"
    if len(raw.encode("utf-8")) <= _MAX_CALLBACK_LEN:
        return raw
    if store is not None:
        ref = _callback_ref(REPLY_CALLBACK_PREFIX.rstrip(":"), value)
        store.put(ref, value, expires_at=time.time() + CALLBACK_REF_TTL)
        return f"{REPLY_CALLBACK_PREFIX}{CALLBACK_REF_MARKER}{ref}"
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{REPLY_CALLBACK_PREFIX}{REPLY_HASH_MARKER}{digest}"


def _encode_select_callback(
    action_id: str,
    value: str,
    store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> str:
    """Build a channel-safe callback payload for a degraded select option.

    The raw ``select:<action_id>:<value>`` form can exceed channel callback
    limits (e.g. Telegram's 64-byte cap). When it fits it is returned unchanged.

    When it overflows and a *store* is available, the canonical value is
    persisted under a short reference and the callback carries
    ``select:<action_id>:@<ref>``; the registry resolves the reference back to
    the exact value on click, so long option values round-trip losslessly.

    Without a store the value is replaced with a short, collision-resistant hash
    so distinct options stay distinct after truncation (but the value cannot be
    recovered — see the issue this addresses).
    """
    raw = f"select:{action_id}:{value}"
    if len(raw.encode("utf-8")) <= _MAX_CALLBACK_LEN:
        return raw
    if store is not None:
        ref = _callback_ref(f"select:{action_id}", value)
        store.put(ref, value, expires_at=time.time() + CALLBACK_REF_TTL)
        prefix = f"select:{action_id}:{CALLBACK_REF_MARKER}"
        if len(prefix.encode("utf-8")) + len(ref) > _MAX_CALLBACK_LEN:
            # action_id itself is long; hash it so the ref still fits the bound.
            aid_digest = hashlib.sha1((action_id or "").encode("utf-8")).hexdigest()[:8]
            prefix = f"select:{aid_digest}:{CALLBACK_REF_MARKER}"
        return f"{prefix}{ref}"
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    prefix = f"select:{action_id}:"
    # Reserve room for the digest; trim the action_id prefix if needed.
    budget = _MAX_CALLBACK_LEN - len(digest)
    if budget < len("select::"):
        # action_id itself is too long; hash it too to guarantee the bound.
        aid_digest = hashlib.sha1((action_id or "").encode("utf-8")).hexdigest()[:8]
        prefix = f"select:{aid_digest}:"
    return f"{prefix[:_MAX_CALLBACK_LEN - len(digest)]}{digest}"


def _select_to_buttons(
    block: PresentationBlock,
    store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> PresentationBlock:
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
                    value=_encode_select_callback(action_id, option.value, store),
                ),
            )
        )
    return PresentationBlock(type=BlockType.BUTTONS, buttons=buttons)


def _clamp_table(
    block: PresentationBlock,
    limits: PresentationLimits,
) -> PresentationBlock:
    """Return a copy of a TABLE block clamped to the channel's row/column caps."""
    columns = list(block.columns or [])
    rows = [list(r) for r in (block.rows or [])]
    if limits.max_table_cols and len(columns) > limits.max_table_cols:
        columns = columns[: limits.max_table_cols]
        rows = [r[: limits.max_table_cols] for r in rows]
    if limits.max_table_rows and len(rows) > limits.max_table_rows:
        rows = rows[: limits.max_table_rows]
    return PresentationBlock(type=BlockType.TABLE, columns=columns, rows=rows)


def table_to_markdown(columns: List[str], rows: List[List[str]]) -> str:
    """Render a table as a deterministic GitHub-flavoured markdown table.

    Cells are coerced to strings and pipes escaped so the table stays valid.
    Short rows are padded and long rows trimmed to the header width.
    """
    def _cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    header = [_cell(c) for c in columns]
    ncols = len(header)
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * ncols) + " |")
    for row in rows:
        cells = [_cell(c) for c in row][:ncols]
        cells += [""] * (ncols - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def chart_to_text(
    chart_kind: Optional[str],
    series: List[Dict[str, Any]],
    caption: Optional[str] = None,
) -> str:
    """Render a chart as a compact, deterministic text summary.

    Produces a caption/kind header followed by one line per series listing its
    label and points, so the data is never silently dropped on channels without
    a native visualisation.
    """
    lines: List[str] = []
    kind = chart_kind or "chart"
    header = caption or f"{kind.capitalize()} chart"
    lines.append(header)
    for entry in series or []:
        label = str(entry.get("label", "series"))
        points = entry.get("points", []) or []
        rendered = ", ".join(str(p) for p in points)
        lines.append(f"{label}: {rendered}")
    return "\n".join(lines)


def _table_to_text_block(block: PresentationBlock) -> PresentationBlock:
    """Degrade a TABLE block to a markdown-table TEXT block."""
    return PresentationBlock(
        type=BlockType.TEXT,
        text=table_to_markdown(block.columns or [], block.rows or []),
    )


def _chart_to_text_block(block: PresentationBlock) -> PresentationBlock:
    """Degrade a CHART block to a text-summary TEXT block."""
    return PresentationBlock(
        type=BlockType.TEXT,
        text=chart_to_text(block.chart_kind, block.series or [], block.text),
    )


def adapt_presentation(
    presentation: MessagePresentation,
    limits: PresentationLimits,
    *,
    callback_store: Optional["CallbackPayloadStoreProtocol"] = None,
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
        callback_store: Optional :class:`CallbackPayloadStoreProtocol`. When a
            ``reply``/``select`` value overflows the channel callback byte-cap
            and a store is supplied, the canonical value is persisted under a
            short reference and the callback carries ``@<ref>`` so the inbound
            registry can resolve the exact value on click. When omitted the
            existing (lossy) hash behaviour is preserved for compatibility.

    Returns:
        A new ``MessagePresentation`` that is safe to render natively.
    """
    adapted_blocks: List[PresentationBlock] = []

    for block in presentation.blocks:
        block_type = block.type.value if isinstance(block.type, BlockType) else block.type

        if block_type == BlockType.SELECT.value and not limits.supports_select:
            # Degrade select -> buttons, then adapt the resulting buttons block
            block = _select_to_buttons(block, callback_store)
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

            adapted_buttons = [_adapt_button(b, limits, callback_store) for b in buttons]
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

        if block_type == BlockType.TABLE.value:
            clamped = _clamp_table(block, limits)
            if limits.supports_tables:
                adapted_blocks.append(clamped)
            else:
                # Degrade to a deterministic markdown table (then clamp text).
                text_block = _table_to_text_block(clamped)
                if (
                    limits.max_text_length
                    and text_block.text
                    and len(text_block.text) > limits.max_text_length
                ):
                    text_block = PresentationBlock(
                        type=BlockType.TEXT,
                        text=text_block.text[: limits.max_text_length],
                    )
                adapted_blocks.append(text_block)
            continue

        if block_type == BlockType.CHART.value:
            if limits.supports_charts:
                adapted_blocks.append(block)
            else:
                # Degrade to a compact text summary (then clamp text).
                text_block = _chart_to_text_block(block)
                if (
                    limits.max_text_length
                    and text_block.text
                    and len(text_block.text) > limits.max_text_length
                ):
                    text_block = PresentationBlock(
                        type=BlockType.TEXT,
                        text=text_block.text[: limits.max_text_length],
                    )
                adapted_blocks.append(text_block)
            continue

        adapted_blocks.append(block)

    return MessagePresentation(
        blocks=adapted_blocks,
        tone=presentation.tone,
        ephemeral=presentation.ephemeral,
        replace_message_id=presentation.replace_message_id,
    )


# Machine-readable degradation reason codes, mirroring the ``REASON_*`` style in
# ``admission.py``/``failure.py`` so a dropped control is recorded, not silent.
DEGRADE_SELECT_UNSUPPORTED = "select_unsupported"
DEGRADE_WEB_APP_UNAVAILABLE = "web_app_unavailable"
DEGRADE_BUTTONS_TRUNCATED = "buttons_truncated"
DEGRADE_OPTIONS_TRUNCATED = "options_truncated"
DEGRADE_TABLE_AS_TEXT = "table_rendered_as_text"
DEGRADE_CHART_AS_TEXT = "chart_rendered_as_text"
DEGRADE_CALLBACK_DATA_TOO_LONG = "callback_data_too_long"


@dataclass(frozen=True)
class DegradedDelivery:
    """A record of controls a channel could not render natively.

    ``adapt_presentation`` already downgrades charts/tables/buttons/selects to
    deterministic text/callbacks, but returns *no record* of what it dropped, so
    the downgrade is silent — the user (and the model) never learns a button
    vanished or a chart became text. This is the typed report of that
    degradation, the presentation-path counterpart of
    :class:`~praisonaiagents.bots.failure.FailureReply`: an adapter appends
    :attr:`fallback_text` so the loss is *visible*, and records
    :attr:`reasons` so it is *machine-readable*.

    Attributes:
        dropped: Human-readable descriptions of each degraded/dropped control
            (e.g. ``"1 button rendered as text"``).
        reasons: Machine-readable reason codes (the ``DEGRADE_*`` constants),
            aligned by intent with ``dropped``.
        fallback_text: A short, user-facing note the adapter can append so the
            degradation is never silent (e.g. ``"(Delivered 1 button as text -
            Telegram callback data exceeded 64 bytes.)"``). Empty when nothing
            degraded.
    """

    dropped: Tuple[str, ...]
    reasons: Tuple[str, ...]
    fallback_text: str


def _callback_is_lossy(value: Optional[str]) -> bool:
    """True when an *adapted* callback value carries the lossy hash marker.

    :func:`_encode_reply_callback` / :func:`_encode_select_callback` emit a
    ``#<digest>`` payload only when the original value overflowed the channel
    byte-cap *and* no store was available to preserve it losslessly. Detecting
    that marker on the already-adapted value is the single source of truth for
    "callback data too long" — so the report never disagrees with the
    adaptation (e.g. no false positive when a store round-trips the value, and
    no miss for a degraded select option).
    """
    if not value:
        return False
    if value.startswith(f"{REPLY_CALLBACK_PREFIX}{REPLY_HASH_MARKER}"):
        return True
    # Degraded select options: ``select:...:`` with no ``@<ref>`` store marker
    # means the value was hashed (lossy). A stored ref carries CALLBACK_REF_MARKER.
    if value.startswith("select:"):
        tail = value.rsplit(":", 1)[-1]
        return not tail.startswith(CALLBACK_REF_MARKER)
    return False


def _presentation_degradation(
    presentation: MessagePresentation,
    limits: PresentationLimits,
    callback_store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> Optional[DegradedDelivery]:
    """Compute the :class:`DegradedDelivery` report for adapting to ``limits``.

    Derives the report from the *same* conversion and selection decisions as
    :func:`adapt_presentation` (select->buttons, priority/cap button truncation,
    web_app->url, option truncation, table/chart->text) — inspecting only the
    controls actually retained and reporting callback shortening only when the
    adapter genuinely produced a lossy payload. Returns ``None`` when nothing
    degrades.
    """
    dropped: List[str] = []
    reasons: List[str] = []

    for block in presentation.blocks:
        block_type = block.type.value if isinstance(block.type, BlockType) else block.type

        if block_type == BlockType.SELECT.value and not limits.supports_select:
            # Follow the adapter: select -> buttons (encoding option callbacks
            # exactly as adapt_presentation does), then treat as a buttons block.
            n = len(block.options or [])
            dropped.append(f"select menu ({n} options) rendered as buttons")
            reasons.append(DEGRADE_SELECT_UNSUPPORTED)
            block = _select_to_buttons(block, callback_store)
            block_type = BlockType.BUTTONS.value

        if block_type == BlockType.BUTTONS.value and block.buttons:
            buttons = list(block.buttons)
            rows = limits.max_button_rows if limits.max_button_rows else 1
            total_cap = limits.max_buttons * rows if limits.max_buttons else len(buttons)
            if total_cap <= 0:
                total_cap = len(buttons)
            if len(buttons) > total_cap:
                n = len(buttons) - total_cap
                dropped.append(f"{n} button(s) dropped (over channel cap)")
                reasons.append(DEGRADE_BUTTONS_TRUNCATED)
                # Only the *retained* buttons are actually rendered; mirror the
                # priority-aware selection so we don't report a dropped
                # button's web_app/callback degradation.
                indexed = list(enumerate(buttons))
                kept = sorted(
                    indexed, key=lambda iv: (iv[1].priority, -iv[0]), reverse=True
                )[:total_cap]
                kept.sort(key=lambda iv: iv[0])
                buttons = [b for _, b in kept]

            for btn in buttons:
                if btn.action is None:
                    continue
                # Compare against the adapter's actual output for this button.
                adapted_btn = _adapt_button(btn, limits, callback_store)
                a_type = (
                    btn.action.type.value
                    if isinstance(btn.action.type, ActionType)
                    else btn.action.type
                )
                if (
                    not limits.supports_web_apps
                    and a_type == ActionType.WEB_APP.value
                    and btn.action.web_app_url
                ):
                    dropped.append("web-app button rendered as URL")
                    reasons.append(DEGRADE_WEB_APP_UNAVAILABLE)
                elif adapted_btn.action is not None and _callback_is_lossy(
                    adapted_btn.action.value
                ):
                    dropped.append("button callback shortened (data exceeded byte cap)")
                    reasons.append(DEGRADE_CALLBACK_DATA_TOO_LONG)

        elif block_type == BlockType.SELECT.value and block.options:
            if limits.max_options and len(block.options) > limits.max_options:
                n = len(block.options) - limits.max_options
                dropped.append(f"{n} select option(s) dropped (over channel cap)")
                reasons.append(DEGRADE_OPTIONS_TRUNCATED)

        elif block_type == BlockType.TABLE.value and not limits.supports_tables:
            dropped.append("table rendered as text")
            reasons.append(DEGRADE_TABLE_AS_TEXT)

        elif block_type == BlockType.CHART.value and not limits.supports_charts:
            dropped.append("chart rendered as text")
            reasons.append(DEGRADE_CHART_AS_TEXT)

    if not dropped:
        return None

    fallback_text = "(" + "; ".join(dropped) + ".)"
    return DegradedDelivery(
        dropped=tuple(dropped),
        reasons=tuple(reasons),
        fallback_text=fallback_text,
    )


def adapt_presentation_with_report(
    presentation: MessagePresentation,
    limits: PresentationLimits,
    *,
    callback_store: Optional["CallbackPayloadStoreProtocol"] = None,
) -> "tuple[MessagePresentation, Optional[DegradedDelivery]]":
    """Adapt a presentation *and* report what degraded.

    Identical to :func:`adapt_presentation` for the returned presentation, but
    additionally returns a typed :class:`DegradedDelivery` (or ``None``) so the
    adapter can append a readable text fallback and record machine-readable
    reasons instead of downgrading silently. ``adapt_presentation`` is retained
    unchanged for callers that do not need the report.

    Returns:
        ``(adapted_presentation, degraded_or_none)``.
    """
    adapted = adapt_presentation(presentation, limits, callback_store=callback_store)
    report = _presentation_degradation(presentation, limits, callback_store)
    return adapted, report


# The renderer contract lives in ``protocols.py`` (alongside the other bot
# extension-point protocols). Re-exported here for backward-compatible imports
# (``from praisonaiagents.bots.presentation import PresentationRendererProtocol``).
from .protocols import PresentationRendererProtocol  # noqa: E402,F401


# Registry keyed by a normalized (lowercased, stripped) platform id. Both
# built-in (registered by the wrapper at import time) and plugin renderers
# register here identically, so no channel is second-class for interactive UX.
# Consumers resolve with ``get_presentation_renderer`` and fall back to plain
# text only when genuinely no renderer exists for a platform.
_PRESENTATION_RENDERERS: Dict[str, type] = {}


def _normalize_platform(platform: str) -> str:
    """Normalize a platform id the same way the channel registry does.

    Channel identifiers are matched case-insensitively elsewhere, so a
    mixed-case plugin id (``"Matrix"``) must resolve to the same renderer slot
    as ``"matrix"``. Without this, a channel could register/resolve as a channel
    but silently miss its renderer and degrade to plain text.
    """
    return platform.strip().lower()


def register_presentation_renderer(platform: str, renderer: type) -> None:
    """Register *renderer* as the presentation renderer for *platform*.

    Any channel — built-in or a pip-installed plugin — calls this (e.g. from its
    ``setup`` hook or entry point) so its interactive presentations render
    natively instead of degrading to plain text. Re-registering a platform
    overrides the previous renderer, letting a plugin intentionally supersede a
    built-in.

    Args:
        platform: The channel/platform id (e.g. ``"telegram"``, ``"matrix"``);
            matched case-insensitively.
        renderer: A class satisfying :class:`PresentationRendererProtocol`
            (exposing ``get_limits`` and ``render``).

    Raises:
        ValueError: If *platform* is empty/blank.
        TypeError: If *renderer* does not expose callable ``get_limits`` and
            ``render`` — so a misconfigured renderer fails loudly at
            registration rather than later inside :func:`render_for`.
    """
    key = _normalize_platform(platform) if isinstance(platform, str) else ""
    if not key:
        raise ValueError(
            "register_presentation_renderer: platform id must be a non-empty "
            "string (e.g. 'telegram', 'matrix')."
        )
    if not (callable(getattr(renderer, "get_limits", None))
            and callable(getattr(renderer, "render", None))):
        raise TypeError(
            "register_presentation_renderer: renderer for "
            f"'{platform}' must satisfy PresentationRendererProtocol — expose "
            "static/callable 'get_limits()' and 'render(presentation)'."
        )
    _PRESENTATION_RENDERERS[key] = renderer


def get_presentation_renderer(platform: str) -> Optional[type]:
    """Return the registered renderer class for *platform*, or ``None``.

    Lookup is case-insensitive to mirror registration.
    """
    if not isinstance(platform, str):
        return None
    return _PRESENTATION_RENDERERS.get(_normalize_platform(platform))


