"""
A2UI (Agent-to-User Interface) Protocol Integration for PraisonAI Agents

This module provides A2UI protocol support, enabling PraisonAI Agents
to generate rich, interactive UIs declaratively via JSON.

A2UI is Google's open standard that allows agents to "speak UI" by sending
declarative JSON describing UI components, which clients then render natively.

Usage:
    from praisonaiagents.ui.a2ui import (
        # Message types
        CreateSurfaceMessage,
        UpdateComponentsMessage,
        UpdateDataModelMessage,
        DeleteSurfaceMessage,
        # Component types
        TextComponent,
        ImageComponent,
        ButtonComponent,
        CardComponent,
        RowComponent,
        ColumnComponent,
        # Extension helpers
        create_a2ui_part,
        is_a2ui_part,
    )
"""

from praisonaiagents.ui.a2ui.types import (
    # Data binding
    PathBinding,
    resolve_string_or_path,
    # Action types
    ActionContext,
    Action,
    # Children types
    ChildrenTemplate,
    # Component types
    TextComponent,
    ImageComponent,
    IconComponent,
    ButtonComponent,
    CardComponent,
    RowComponent,
    ColumnComponent,
    ListComponent,
    TextFieldComponent,
    CheckBoxComponent,
    SliderComponent,
    DateTimeInputComponent,
    # Message types
    CreateSurfaceMessage,
    UpdateComponentsMessage,
    UpdateDataModelMessage,
    DeleteSurfaceMessage,
    # Data part
    A2UIDataPart,
)

from praisonaiagents.ui.a2ui.extension import (
    A2UI_MIME_TYPE,
    A2UI_EXTENSION_URI,
    STANDARD_CATALOG_ID,
    create_a2ui_part,
    is_a2ui_part,
    get_a2ui_agent_extension,
    AgentExtension,
)

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.agent import A2UIAgent
from praisonaiagents.ui.a2ui.templates import (
    ChatTemplate,
    ListTemplate,
    FormTemplate,
    DashboardTemplate,
)

__all__ = [
    # Data binding
    "PathBinding",
    "resolve_string_or_path",
    # Action types
    "ActionContext",
    "Action",
    # Children types
    "ChildrenTemplate",
    # Component types
    "TextComponent",
    "ImageComponent",
    "IconComponent",
    "ButtonComponent",
    "CardComponent",
    "RowComponent",
    "ColumnComponent",
    "ListComponent",
    "TextFieldComponent",
    "CheckBoxComponent",
    "SliderComponent",
    "DateTimeInputComponent",
    # Message types
    "CreateSurfaceMessage",
    "UpdateComponentsMessage",
    "UpdateDataModelMessage",
    "DeleteSurfaceMessage",
    # Data part
    "A2UIDataPart",
    # Extension
    "A2UI_MIME_TYPE",
    "A2UI_EXTENSION_URI",
    "STANDARD_CATALOG_ID",
    "create_a2ui_part",
    "is_a2ui_part",
    "get_a2ui_agent_extension",
    "AgentExtension",
    # Surface builder
    "Surface",
    # Agent wrapper
    "A2UIAgent",
    # Templates
    "ChatTemplate",
    "ListTemplate",
    "FormTemplate",
    "DashboardTemplate",
]
