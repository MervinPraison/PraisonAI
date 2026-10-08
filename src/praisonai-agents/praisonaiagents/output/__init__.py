"""
Output Styles Module for PraisonAI Agents.

Provides configurable output formatting:
- Predefined styles (concise, detailed, technical, etc.)
- Custom formatting rules
- Markdown/plain text/JSON output
- Response length control

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Styles only applied when configured
- No overhead when not in use

Usage:
    from praisonaiagents.output import OutputStyle, OutputFormatter
    
    # Use predefined style
    style = OutputStyle.concise()
    
    # Apply to agent
    agent = Agent(
        instructions="...",
        output_style=style
    )
    
    # Or format manually
    formatter = OutputFormatter(style)
    formatted = formatter.format(response)
"""

from .._lazy import create_lazy_getattr

__all__ = [
    # Core classes
    "OutputStyle",
    "OutputFormatter",
    # Style presets
    "StylePreset",
    # Configuration
    "OutputConfig",
    # Status output (for status preset - no timestamps)
    "StatusOutput",
    "enable_status_output",
    "disable_status_output",
    "is_status_output_enabled",
    "get_status_output",
    # Trace output (for trace preset - with timestamps)
    "TraceOutput",
    "enable_trace_output",
    "disable_trace_output",
    "is_trace_output_enabled",
    "get_trace_output",
    # Editor output (for editor preset - beginner-friendly numbered steps)
    "EditorOutput",
    "enable_editor_output",
    "disable_editor_output",
    "is_editor_output_enabled",
    "get_editor_output",
    "TOOL_LABELS",
    "BlockType",
    "DisplayBlock",
]


_LAZY_IMPORTS = {
    "OutputStyle": ("praisonaiagents.output.style", "OutputStyle"),
    "OutputFormatter": ("praisonaiagents.output.formatter", "OutputFormatter"),
    "StylePreset": ("praisonaiagents.output.style", "StylePreset"),
    # Consolidated to the canonical config.OutputConfig (see issue #2294).
    # The former divergent dataclass in output/config.py was unused; this
    # import path is preserved for backward compatibility.
    "OutputConfig": ("praisonaiagents.config", "OutputConfig"),
    # Status output (for status preset - no timestamps)
    "StatusOutput": ("praisonaiagents.output.status", "StatusOutput"),
    "enable_status_output": ("praisonaiagents.output.status", "enable_status_output"),
    "disable_status_output": ("praisonaiagents.output.status", "disable_status_output"),
    "is_status_output_enabled": ("praisonaiagents.output.status", "is_status_output_enabled"),
    "get_status_output": ("praisonaiagents.output.status", "get_status_output"),
    # Trace output (for trace preset - with timestamps)
    "TraceOutput": ("praisonaiagents.output.trace", "TraceOutput"),
    "enable_trace_output": ("praisonaiagents.output.trace", "enable_trace_output"),
    "disable_trace_output": ("praisonaiagents.output.trace", "disable_trace_output"),
    "is_trace_output_enabled": ("praisonaiagents.output.trace", "is_trace_output_enabled"),
    "get_trace_output": ("praisonaiagents.output.trace", "get_trace_output"),
    # Editor output (for editor preset - beginner-friendly numbered steps)
    "EditorOutput": ("praisonaiagents.output.editor", "EditorOutput"),
    "enable_editor_output": ("praisonaiagents.output.editor", "enable_editor_output"),
    "disable_editor_output": ("praisonaiagents.output.editor", "disable_editor_output"),
    "is_editor_output_enabled": ("praisonaiagents.output.editor", "is_editor_output_enabled"),
    "get_editor_output": ("praisonaiagents.output.editor", "get_editor_output"),
    "TOOL_LABELS": ("praisonaiagents.output.editor", "TOOL_LABELS"),
    "BlockType": ("praisonaiagents.output.editor", "BlockType"),
    "DisplayBlock": ("praisonaiagents.output.editor", "DisplayBlock"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
