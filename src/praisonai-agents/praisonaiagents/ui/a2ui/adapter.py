"""
Thin adapter over Google's a2ui-agent-sdk (optional dependency).

Install: pip install praisonaiagents[a2ui]
Spec: https://github.com/google/A2UI
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from praisonaiagents.ui.protocols import A2UI_MIME_TYPE


_A2UI_INSTALL_HINT = (
    "A2UI support requires the optional dependency. "
    "Install with: pip install praisonaiagents[a2ui]"
)


def _import(name: str):
    try:
        import importlib

        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(
            f"{_A2UI_INSTALL_HINT} "
            f"(failed to import '{name}'; "
            "if already installed, ensure a2a-sdk>=0.3.0,<1.0.0 and not a2a-sdk 1.x)"
        ) from exc


def _load_a2a_parts_module():
    """Import A2A part helpers from the SDK (module path varies by SDK version)."""
    for name in ("a2ui.a2a.parts", "a2ui.a2a"):
        try:
            return _import(name)
        except ImportError:
            continue
    return None


def _normalize_a2ui_payload(a2ui_data: Dict[str, Any]) -> Dict[str, Any]:
    if "messages" in a2ui_data:
        return a2ui_data
    if any(k in a2ui_data for k in ("createSurface", "updateComponents", "updateDataModel")):
        return {"messages": [a2ui_data]}
    return a2ui_data


def _local_create_a2ui_part(a2ui_data: Dict[str, Any]) -> Any:
    """Fallback when a2ui-agent-sdk no longer ships ``a2ui.a2a.parts`` (e.g. 0.12+)."""
    payload = _normalize_a2ui_payload(a2ui_data)
    root = SimpleNamespace(
        data=payload,
        metadata={"mimeType": A2UI_MIME_TYPE},
    )
    return SimpleNamespace(root=root)


def _local_is_a2ui_part(part: Any) -> bool:
    root = getattr(part, "root", part)
    metadata = getattr(root, "metadata", None) or {}
    if isinstance(metadata, dict) and metadata.get("mimeType") == A2UI_MIME_TYPE:
        return True
    data = getattr(root, "data", None)
    if isinstance(data, dict) and "messages" in data:
        return True
    return False


def create_a2ui_part(a2ui_data: Dict[str, Any]) -> Any:
    """Wrap A2UI payload for A2A transport (MIME: application/json+a2ui)."""
    parts = _load_a2a_parts_module()
    if parts is not None and hasattr(parts, "create_a2ui_part"):
        return parts.create_a2ui_part(a2ui_data)
    try:
        _import("a2ui")
    except ImportError as exc:
        raise ImportError(_A2UI_INSTALL_HINT) from exc
    return _local_create_a2ui_part(a2ui_data)


def is_a2ui_part(part: Any) -> bool:
    """Return True if an A2A part contains A2UI data."""
    parts = _load_a2a_parts_module()
    if parts is not None and hasattr(parts, "is_a2ui_part"):
        return parts.is_a2ui_part(part)
    return _local_is_a2ui_part(part)


def parse_a2ui_response(text: str) -> List[Any]:
    """Parse and split LLM text into A2A parts (text + validated A2UI JSON)."""
    parser = _import("a2ui.parser.parser")
    return parser.parse_response(text)


def get_schema_manager(
    version: str = "0.9",
    catalogs: Optional[List[Any]] = None,
    accepts_inline_catalogs: bool = False,
) -> Any:
    """Create an A2uiSchemaManager for LLM system prompts and validation."""
    constants = _import("a2ui.schema.constants")
    manager = _import("a2ui.schema.manager")
    basic = _import("a2ui.basic_catalog.provider")

    version_const = constants.VERSION_0_9 if version == "0.9" else version
    catalog_configs = catalogs
    if catalog_configs is None:
        catalog_configs = [basic.BasicCatalog.get_config(version=version_const)]

    return manager.A2uiSchemaManager(
        version=version_const,
        catalogs=catalog_configs,
        accepts_inline_catalogs=accepts_inline_catalogs,
    )


def generate_a2ui_system_prompt(
    role_description: str,
    workflow_description: str = "",
    ui_description: str = "",
    *,
    version: str = "0.9",
    include_schema: bool = True,
    include_examples: bool = True,
) -> str:
    """Build an LLM system prompt with embedded A2UI schema and examples."""
    schema_manager = get_schema_manager(version=version)
    return schema_manager.generate_system_prompt(
        role_description=role_description,
        workflow_description=workflow_description,
        ui_description=ui_description,
        include_schema=include_schema,
        include_examples=include_examples,
    )
