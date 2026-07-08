"""
Computer Use tools for PraisonAI Agents (Issue #516).

Agent-centric computer control — agents call these tools to take screenshots,
move/click the mouse, type text, press keys, and scroll.  No changes to the
Agent class required; this mirrors the ``schedule_tools`` pattern and the
TypeScript ``computer-use`` integration.

Design:
- Safe by default: control actions (click/type/key/scroll/move) require an
  approval callback.  When none is registered they are refused, so an agent
  can never take over the machine without an explicit opt-in.
- Optional dependency: the concrete backend uses ``pyautogui`` which is
  lazy-imported only when a tool actually runs.  Install with
  ``pip install pyautogui``.  Without it the tools return a clear message
  instead of raising at import time (no hot-path / import cost).

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import (
        computer_screenshot, computer_click, computer_type,
        computer_key, computer_scroll, computer_move, set_computer_approval,
    )

    # Opt in to control actions (default denies everything but screenshots)
    set_computer_approval(lambda action: input(f"Approve {action}? (y/n) ") == "y")

    agent = Agent(
        name="assistant",
        instructions="You can control the computer to help the user.",
        tools=[computer_screenshot, computer_click, computer_type,
               computer_key, computer_scroll, computer_move],
    )
    agent.start("Take a screenshot and describe what's on screen")
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)

_MISSING_BACKEND_MSG = (
    "Computer Use backend unavailable: install the optional dependency with "
    "`pip install pyautogui` to enable real screen control."
)

# ── approval gate (safe by default) ──────────────────────────────────────────

_approval_lock = threading.Lock()
_approval_callback: Optional[Callable[[str], bool]] = None


def set_computer_approval(callback: Optional[Callable[[str], bool]]) -> None:
    """Register a human-in-the-loop approval callback for control actions.

    The callback receives a human-readable action description (e.g.
    ``"click(100, 200, left)"``) and must return ``True`` to allow it.
    Pass ``None`` to clear the callback (control actions are then denied).

    Screenshots and screen-size queries are read-only and never gated.
    """
    global _approval_callback
    with _approval_lock:
        _approval_callback = callback


def _approve(action: str) -> bool:
    with _approval_lock:
        callback = _approval_callback
    if callback is None:
        return False
    try:
        return bool(callback(action))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Computer Use approval callback errored: %s", exc)
        return False


# ── lazy backend ─────────────────────────────────────────────────────────────

def _get_backend():
    """Lazy-import ``pyautogui``. Returns the module or ``None`` if missing."""
    try:
        import pyautogui  # type: ignore
    except Exception:  # ImportError or platform (no display) errors
        return None
    return pyautogui


# ── tools ────────────────────────────────────────────────────────────────────

def computer_screenshot(path: str = "") -> str:
    """Take a screenshot of the current screen.

    Capturing the screen is read-only and never gated.  Saving to disk is a
    write operation: when ``path`` is provided it goes through the approval
    gate so an agent cannot overwrite arbitrary files without an explicit
    human opt-in.

    Args:
        path: Optional file path to save the screenshot to. When empty, the
            screenshot is captured but not written to disk.

    Returns:
        A message describing the screenshot size and save path, or an error
        message when the backend is unavailable or the write is denied.
    """
    if path:
        action = f"screenshot_save({path!r})"
        if not _approve(action):
            return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        image = backend.screenshot()
        width, height = image.size
        if path:
            image.save(path)
            return f"Screenshot captured ({width}x{height}) and saved to {path}"
        return f"Screenshot captured ({width}x{height})"
    except Exception as exc:
        return f"Screenshot failed: {exc}"


def computer_screen_size() -> str:
    """Return the screen size as ``"WIDTHxHEIGHT"`` (read-only)."""
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        width, height = backend.size()
        return f"{width}x{height}"
    except Exception as exc:
        return f"Screen size unavailable: {exc}"


def computer_move(x: int, y: int) -> str:
    """Move the mouse cursor to the given screen coordinates (requires approval).

    Args:
        x: Target X coordinate in pixels.
        y: Target Y coordinate in pixels.
    """
    action = f"move({x}, {y})"
    if not _approve(action):
        return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        backend.moveTo(x, y)
        return f"Moved to ({x}, {y})"
    except Exception as exc:
        return f"Move failed: {exc}"


def computer_click(x: int, y: int, button: str = "left") -> str:
    """Click the mouse at the given coordinates (requires approval).

    Args:
        x: Target X coordinate in pixels.
        y: Target Y coordinate in pixels.
        button: Mouse button — ``"left"``, ``"right"`` or ``"middle"``.
    """
    action = f"click({x}, {y}, {button})"
    if not _approve(action):
        return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        backend.click(x=x, y=y, button=button)
        return f"Clicked ({x}, {y}) with {button} button"
    except Exception as exc:
        return f"Click failed: {exc}"


def computer_type(text: str) -> str:
    """Type text using the keyboard (requires approval).

    Args:
        text: The text to type at the current focus.
    """
    action = f"type({text!r})"
    if not _approve(action):
        return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        backend.typewrite(text)
        # typewrite silently skips characters outside the ASCII printable set
        # (unicode, emoji, accented letters). Report only what was delivered.
        typed = sum(1 for c in text if c.isascii() and c.isprintable())
        if typed == len(text):
            return f"Typed {typed} characters"
        return f"Typed {typed} of {len(text)} characters (non-ASCII skipped)"
    except Exception as exc:
        return f"Type failed: {exc}"


def computer_key(key: str) -> str:
    """Press a key or key combination (requires approval).

    Args:
        key: A single key (``"enter"``) or a combination joined by ``"+"``
            (e.g. ``"ctrl+c"``).
    """
    action = f"key({key})"
    if not _approve(action):
        return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        keys = [k.strip() for k in key.split("+") if k.strip()]
        if not keys:
            return f"Key press failed: empty or invalid key string {key!r}"
        if len(keys) > 1:
            backend.hotkey(*keys)
        else:
            backend.press(keys[0])
        return f"Pressed {key}"
    except Exception as exc:
        return f"Key press failed: {exc}"


def computer_scroll(direction: str = "down", amount: int = 3) -> str:
    """Scroll the screen (requires approval).

    Args:
        direction: ``"up"`` or ``"down"``.
        amount: Number of scroll clicks (positive integer).
    """
    action = f"scroll({direction}, {amount})"
    if not _approve(action):
        return f"Action denied: {action}"
    backend = _get_backend()
    if backend is None:
        return _MISSING_BACKEND_MSG
    try:
        if direction not in ("up", "down"):
            return (
                f"Scroll failed: invalid direction {direction!r} "
                "(expected 'up' or 'down')"
            )
        clicks = abs(int(amount))
        backend.scroll(clicks if direction == "up" else -clicks)
        return f"Scrolled {direction} by {clicks}"
    except Exception as exc:
        return f"Scroll failed: {exc}"
