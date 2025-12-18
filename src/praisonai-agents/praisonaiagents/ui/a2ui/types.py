"""
A2UI Protocol Types

Pydantic-style classes for the A2UI (Agent-to-User Interface) protocol.
Based on the A2UI Specification v0.9.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


# =============================================================================
# Data Binding Types
# =============================================================================

@dataclass
class PathBinding:
    """
    A reference to a value in the data model.
    
    Used for data binding in A2UI components.
    """
    path: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"path": self.path}


# Type alias for values that can be literal or path-bound
StringOrPath = Union[str, PathBinding]
NumberOrPath = Union[int, float, PathBinding]
BooleanOrPath = Union[bool, PathBinding]


def resolve_string_or_path(value: StringOrPath) -> Union[str, Dict[str, str]]:
    """Resolve a StringOrPath to its serialized form."""
    if isinstance(value, PathBinding):
        return value.to_dict()
    return value


def resolve_number_or_path(value: NumberOrPath) -> Union[int, float, Dict[str, str]]:
    """Resolve a NumberOrPath to its serialized form."""
    if isinstance(value, PathBinding):
        return value.to_dict()
    return value


def resolve_boolean_or_path(value: BooleanOrPath) -> Union[bool, Dict[str, str]]:
    """Resolve a BooleanOrPath to its serialized form."""
    if isinstance(value, PathBinding):
        return value.to_dict()
    return value


# =============================================================================
# Action Types
# =============================================================================

@dataclass
class ActionContext:
    """
    A key-value pair for action context.
    
    Used to pass data from UI to action handlers.
    """
    key: str
    value: Union[str, int, float, bool, PathBinding]
    
    def to_dict(self) -> Dict[str, Any]:
        if isinstance(self.value, PathBinding):
            return {"key": self.key, "value": self.value.to_dict()}
        return {"key": self.key, "value": self.value}


@dataclass
class Action:
    """
    An action triggered by a UI component (e.g., button click).
    """
    name: str
    context: List[ActionContext] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "context": [c.to_dict() for c in self.context]
        }


# =============================================================================
# Children Types
# =============================================================================

@dataclass
class ChildrenTemplate:
    """
    A template for generating dynamic children from a data model list.
    """
    component_id: str
    path: str
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "componentId": self.component_id,
            "path": self.path
        }


# Type alias for children - either explicit list or template
ChildrenType = Union[List[str], ChildrenTemplate]


def resolve_children(children: ChildrenType) -> Union[List[str], Dict[str, str]]:
    """Resolve children to serialized form."""
    if isinstance(children, ChildrenTemplate):
        return children.to_dict()
    return children


# =============================================================================
# Component Types
# =============================================================================

class UsageHint(str, Enum):
    """Text usage hints for styling."""
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4"
    H5 = "h5"
    CAPTION = "caption"
    BODY = "body"


class ImageFit(str, Enum):
    """Image fit options."""
    CONTAIN = "contain"
    COVER = "cover"
    FILL = "fill"
    NONE = "none"
    SCALE_DOWN = "scale-down"


class ImageUsageHint(str, Enum):
    """Image usage hints."""
    ICON = "icon"
    AVATAR = "avatar"
    SMALL_FEATURE = "smallFeature"
    MEDIUM_FEATURE = "mediumFeature"
    LARGE_FEATURE = "largeFeature"
    HEADER = "header"


@dataclass
class TextComponent:
    """Text display component."""
    id: str
    text: StringOrPath
    usage_hint: Optional[str] = None
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Text",
            "text": resolve_string_or_path(self.text)
        }
        if self.usage_hint:
            result["usageHint"] = self.usage_hint
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class ImageComponent:
    """Image display component."""
    id: str
    url: StringOrPath
    fit: Optional[str] = None
    usage_hint: Optional[str] = None
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Image",
            "url": resolve_string_or_path(self.url)
        }
        if self.fit:
            result["fit"] = self.fit
        if self.usage_hint:
            result["usageHint"] = self.usage_hint
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class IconComponent:
    """Icon display component."""
    id: str
    name: StringOrPath
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Icon",
            "name": resolve_string_or_path(self.name)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class ButtonComponent:
    """Button component with action."""
    id: str
    child: str
    action: Optional[Action] = None
    primary: bool = False
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Button",
            "child": self.child
        }
        if self.primary:
            result["primary"] = True
        if self.action:
            result["action"] = self.action.to_dict()
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class CardComponent:
    """Card container component."""
    id: str
    child: str
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Card",
            "child": self.child
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class RowComponent:
    """Horizontal layout component."""
    id: str
    children: ChildrenType
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Row",
            "children": resolve_children(self.children)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class ColumnComponent:
    """Vertical layout component."""
    id: str
    children: ChildrenType
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Column",
            "children": resolve_children(self.children)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class ListComponent:
    """List component for repeating items."""
    id: str
    children: ChildrenType
    direction: str = "vertical"
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "List",
            "direction": self.direction,
            "children": resolve_children(self.children)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class TextFieldComponent:
    """Text input field component."""
    id: str
    label: StringOrPath
    text: StringOrPath
    field_type: str = "text"
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "TextField",
            "label": resolve_string_or_path(self.label),
            "text": resolve_string_or_path(self.text),
            "type": self.field_type
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class CheckBoxComponent:
    """Checkbox input component."""
    id: str
    label: StringOrPath
    checked: BooleanOrPath = False
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "CheckBox",
            "label": resolve_string_or_path(self.label),
            "checked": resolve_boolean_or_path(self.checked)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class SliderComponent:
    """Slider input component."""
    id: str
    min_value: NumberOrPath
    max_value: NumberOrPath
    value: NumberOrPath
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "Slider",
            "min": resolve_number_or_path(self.min_value),
            "max": resolve_number_or_path(self.max_value),
            "value": resolve_number_or_path(self.value)
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class DateTimeInputComponent:
    """Date/time input component."""
    id: str
    label: StringOrPath
    value: StringOrPath
    enable_date: bool = True
    enable_time: bool = False
    weight: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "component": "DateTimeInput",
            "label": resolve_string_or_path(self.label),
            "value": resolve_string_or_path(self.value),
            "enableDate": self.enable_date,
            "enableTime": self.enable_time
        }
        if self.weight is not None:
            result["weight"] = self.weight
        return result


# Type alias for any component
Component = Union[
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
]


# =============================================================================
# Message Types
# =============================================================================

@dataclass
class CreateSurfaceMessage:
    """
    Message to create a new UI surface.
    
    Signals the client to create a new surface and begin rendering it.
    """
    surface_id: str
    catalog_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "createSurface": {
                "surfaceId": self.surface_id,
                "catalogId": self.catalog_id
            }
        }


@dataclass
class UpdateComponentsMessage:
    """
    Message to update surface components.
    
    Updates a surface with a new set of components.
    """
    surface_id: str
    components: List[Component]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "updateComponents": {
                "surfaceId": self.surface_id,
                "components": [c.to_dict() for c in self.components]
            }
        }


@dataclass
class UpdateDataModelMessage:
    """
    Message to update the data model.
    
    Updates the data model for an existing surface.
    """
    surface_id: str
    value: Any
    path: str = "/"
    op: str = "replace"
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "updateDataModel": {
                "surfaceId": self.surface_id,
                "path": self.path,
                "op": self.op,
                "value": self.value
            }
        }
        return result


@dataclass
class DeleteSurfaceMessage:
    """
    Message to delete a surface.
    
    Signals the client to delete the surface.
    """
    surface_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "deleteSurface": {
                "surfaceId": self.surface_id
            }
        }


# =============================================================================
# Data Part Type
# =============================================================================

@dataclass
class A2UIDataPart:
    """
    A2UI data part for A2A integration.
    
    Wraps A2UI data with the appropriate MIME type.
    """
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"data": self.data}
        if self.metadata:
            result["metadata"] = self.metadata
        return result
