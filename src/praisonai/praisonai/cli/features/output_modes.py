"""
Output Modes for PraisonAI CLI.

Provides compact, verbose, and quiet output modes.
"""

import os
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class OutputMode(Enum):
    """CLI output modes."""
    COMPACT = "compact"
    VERBOSE = "verbose"
    QUIET = "quiet"


@dataclass
class OutputConfig:
    """Output configuration."""
    mode: OutputMode = OutputMode.VERBOSE
    color: bool = True
    show_timestamps: bool = False
    max_width: int = 120


# Global output mode
_current_mode: OutputMode = OutputMode.VERBOSE
_output_config: Optional[OutputConfig] = None


def get_default_mode() -> OutputMode:
    """Get the default output mode."""
    # Check environment variable
    env_mode = os.environ.get("PRAISON_OUTPUT_MODE", "").lower()
    if env_mode == "compact":
        return OutputMode.COMPACT
    elif env_mode == "quiet":
        return OutputMode.QUIET
    return OutputMode.VERBOSE


def get_output_mode() -> OutputMode:
    """Get the current output mode."""
    return _current_mode


def set_output_mode(mode: OutputMode) -> None:
    """Set the current output mode."""
    global _current_mode
    _current_mode = mode


def get_output_config() -> OutputConfig:
    """Get the output configuration."""
    global _output_config
    if _output_config is None:
        _output_config = OutputConfig(mode=get_default_mode())
    return _output_config


def set_output_config(config: OutputConfig) -> None:
    """Set the output configuration."""
    global _output_config
    _output_config = config


def is_compact() -> bool:
    """Check if compact mode is enabled."""
    return get_output_mode() == OutputMode.COMPACT


def is_quiet() -> bool:
    """Check if quiet mode is enabled."""
    return get_output_mode() == OutputMode.QUIET


def is_verbose() -> bool:
    """Check if verbose mode is enabled."""
    return get_output_mode() == OutputMode.VERBOSE


class OutputHandler:
    """
    Handler for formatted output based on current mode.
    
    Usage:
        handler = OutputHandler()
        handler.info("Processing file...")
        handler.success("Done!")
        handler.error("Something went wrong")
    """
    
    def __init__(self, mode: Optional[OutputMode] = None):
        self.mode = mode or get_output_mode()
        self._console = None
    
    @property
    def console(self):
        """Lazy load Rich console."""
        if self._console is None:
            from rich.console import Console
            self._console = Console()
        return self._console
    
    def info(self, message: str) -> None:
        """Print info message."""
        if self.mode == OutputMode.QUIET:
            return
        if self.mode == OutputMode.COMPACT:
            print(f"ℹ {message}")
        else:
            self.console.print(f"[blue]ℹ[/blue] {message}")
    
    def success(self, message: str) -> None:
        """Print success message."""
        if self.mode == OutputMode.QUIET:
            return
        if self.mode == OutputMode.COMPACT:
            print(f"✓ {message}")
        else:
            self.console.print(f"[green]✓[/green] {message}")
    
    def warning(self, message: str) -> None:
        """Print warning message."""
        if self.mode == OutputMode.COMPACT:
            print(f"⚠ {message}")
        else:
            self.console.print(f"[yellow]⚠[/yellow] {message}")
    
    def error(self, message: str) -> None:
        """Print error message."""
        if self.mode == OutputMode.COMPACT:
            print(f"✗ {message}")
        else:
            self.console.print(f"[red]✗[/red] {message}")
    
    def debug(self, message: str) -> None:
        """Print debug message (only in verbose mode)."""
        if self.mode == OutputMode.VERBOSE:
            self.console.print(f"[dim]DEBUG: {message}[/dim]")
    
    def print(self, message: str) -> None:
        """Print message regardless of mode."""
        if self.mode == OutputMode.QUIET:
            return
        print(message)
