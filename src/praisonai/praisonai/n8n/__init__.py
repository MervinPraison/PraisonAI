"""
n8n Integration for PraisonAI Workflows

This module provides bidirectional conversion between PraisonAI YAML workflows
and n8n JSON format for visual workflow editing.

Features:
- Convert PraisonAI YAML workflows to n8n JSON format
- Reverse conversion from n8n JSON back to YAML
- CLI commands for export, import, and preview
- n8n API integration for workflow management

Example:
    from praisonai.n8n import YAMLToN8nConverter, preview_workflow
    
    converter = YAMLToN8nConverter()
    n8n_json = converter.convert(yaml_workflow)
    
    # Preview in n8n UI
    preview_workflow("my-workflow.yaml")
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .converter import YAMLToN8nConverter
    from .reverse_converter import N8nToYAMLConverter
    from .preview import preview_workflow
    from .client import N8nClient

# Lazy imports for optional dependencies
def __getattr__(name: str):
    if name == "YAMLToN8nConverter":
        from .converter import YAMLToN8nConverter
        return YAMLToN8nConverter
    elif name == "N8nToYAMLConverter":
        from .reverse_converter import N8nToYAMLConverter
        return N8nToYAMLConverter
    elif name == "preview_workflow":
        from .preview import preview_workflow
        return preview_workflow
    elif name == "N8nClient":
        from .client import N8nClient
        return N8nClient
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "YAMLToN8nConverter",
    "N8nToYAMLConverter", 
    "preview_workflow",
    "N8nClient",
]