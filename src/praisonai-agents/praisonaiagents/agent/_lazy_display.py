"""
Shared lazy-loaders for display utilities used across the Agent class and mixins.

These helpers defer importing rich and the heavy ``..main`` display module until
first use, which keeps import time low for silent mode and avoids circular
imports during package initialisation. Results are cached in module globals and
protected by per-resource locks using double-checked locking, so each import is
resolved at most once across threads. Independent resources use separate locks so
that a slow first import of one does not stall initialisation of the others.
"""

import threading

# Lazy-loaded modules (populated on first use, each protected by its own lock)
_console_lock = threading.Lock()
_live_lock = threading.Lock()
_main_module_lock = threading.Lock()
_rich_console = None
_rich_live = None
_main_module = None


def _get_console():
    """Lazy load rich.console.Console (thread-safe)."""
    global _rich_console
    if _rich_console is None:
        with _console_lock:
            if _rich_console is None:
                from rich.console import Console
                _rich_console = Console
    return _rich_console


def _get_live():
    """Lazy load rich.live.Live (thread-safe)."""
    global _rich_live
    if _rich_live is None:
        with _live_lock:
            if _rich_live is None:
                from rich.live import Live
                _rich_live = Live
    return _rich_live


def _get_display_functions():
    """Lazy load display functions from main module (thread-safe)."""
    global _main_module
    if _main_module is None:
        with _main_module_lock:
            if _main_module is None:
                from ..main import (
                    display_error,
                    display_instruction,
                    display_interaction,
                    display_generating,
                    display_self_reflection,
                    ReflectionOutput,
                    adisplay_instruction,
                    execute_sync_callback
                )
                _main_module = {
                    'display_error': display_error,
                    'display_instruction': display_instruction,
                    'display_interaction': display_interaction,
                    'display_generating': display_generating,
                    'display_self_reflection': display_self_reflection,
                    'ReflectionOutput': ReflectionOutput,
                    'adisplay_instruction': adisplay_instruction,
                    'execute_sync_callback': execute_sync_callback,
                }
    return _main_module
