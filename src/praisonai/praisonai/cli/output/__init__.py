"""
PraisonAI CLI Output Module.

Provides consistent output formatting across all CLI commands.
Supports multiple output modes: text, json, stream-json, screen-reader, quiet, verbose.
"""

from .console import OutputController, OutputMode, get_output_controller, set_output_controller
from .event_bridge import (
    SCHEMA_VERSION,
    StreamEventBridge,
    attach_bridge,
    detach_bridge,
)

__all__ = [
    'OutputController',
    'OutputMode',
    'get_output_controller',
    'set_output_controller',
    'SCHEMA_VERSION',
    'StreamEventBridge',
    'attach_bridge',
    'detach_bridge',
]
