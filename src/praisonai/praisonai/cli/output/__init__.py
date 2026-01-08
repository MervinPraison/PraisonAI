"""
PraisonAI CLI Output Module.

Provides consistent output formatting across all CLI commands.
Supports multiple output modes: text, json, stream-json, screen-reader, quiet, verbose.
"""

from .console import OutputController, OutputMode, get_output_controller, set_output_controller

__all__ = [
    'OutputController',
    'OutputMode',
    'get_output_controller',
    'set_output_controller',
]
