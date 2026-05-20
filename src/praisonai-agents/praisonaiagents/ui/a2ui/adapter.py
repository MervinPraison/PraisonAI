"""
Thin adapter over Google's a2ui-agent-sdk (optional dependency).

Install: pip install praisonaiagents[a2ui]
Spec: https://github.com/google/A2UI
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def create_a2ui_part(a2ui_data: Dict[str, Any]) -> Any:
    """Wrap A2UI payload for A2A transport (MIME: application/json+a2ui)."""
    parts = _import("a2ui.a2a.parts")
    return parts.create_a2ui_part(a2ui_data)


def is_a2ui_part(part: Any) -> bool:
    """Return True if an A2A part contains A2UI data."""
    parts = _import("a2ui.a2a.parts")
    return parts.is_a2ui_part(part)


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
