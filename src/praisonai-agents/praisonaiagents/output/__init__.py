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
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "OutputStyle":
        from .style import OutputStyle
        return OutputStyle
    
    if name == "OutputFormatter":
        from .formatter import OutputFormatter
        return OutputFormatter
    
    if name == "StylePreset":
        from .style import StylePreset
        return StylePreset
    
    if name == "OutputConfig":
        from .config import OutputConfig
        return OutputConfig
    
    # Status output (for status preset - no timestamps)
    if name == "StatusOutput":
        from .status import StatusOutput
        return StatusOutput
    
    if name == "enable_status_output":
        from .status import enable_status_output
        return enable_status_output
    
    if name == "disable_status_output":
        from .status import disable_status_output
        return disable_status_output
    
    if name == "is_status_output_enabled":
        from .status import is_status_output_enabled
        return is_status_output_enabled
    
    if name == "get_status_output":
        from .status import get_status_output
        return get_status_output
    
    # Trace output (for trace preset - with timestamps)
    if name == "TraceOutput":
        from .trace import TraceOutput
        return TraceOutput
    
    if name == "enable_trace_output":
        from .trace import enable_trace_output
        return enable_trace_output
    
    if name == "disable_trace_output":
        from .trace import disable_trace_output
        return disable_trace_output
    
    if name == "is_trace_output_enabled":
        from .trace import is_trace_output_enabled
        return is_trace_output_enabled
    
    if name == "get_trace_output":
        from .trace import get_trace_output
        return get_trace_output
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
