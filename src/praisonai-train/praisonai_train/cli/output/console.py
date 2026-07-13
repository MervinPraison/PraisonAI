"""Output controller for the praisonai-train CLI.

When ``praisonai-code`` is co-installed, this transparently delegates to its
full-featured ``OutputController`` (text/json/stream-json/screen-reader modes)
so the train CLI matches the rest of the toolchain. When train is installed
standalone (only ``rich``/``typer``), a minimal built-in controller provides
the same surface used by ``praisonai_train.cli.commands.train``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, List, Optional

from praisonai_train._code_bridge import code_available, import_code_module


class _FallbackOutputController:
    """Minimal, dependency-light OutputController for standalone train installs.

    Implements only the methods used by the train CLI. Uses ``rich`` when
    available (a core train dependency) and degrades to plain ``print``.
    """

    is_json_mode = False

    def _rich_console(self):
        try:
            from rich.console import Console

            return Console()
        except Exception:
            return None

    def print(self, message: str, style: Optional[str] = None, **kwargs: Any) -> None:
        console = self._rich_console()
        if console is not None:
            try:
                console.print(message, style=style)
                return
            except Exception:
                pass
        print(message)

    def print_error(
        self,
        message: str,
        code: Optional[str] = None,
        remediation: Optional[str] = None,
    ) -> None:
        print(f"ERROR: {message}", file=sys.stderr)
        if remediation:
            print(f"FIX: {remediation}", file=sys.stderr)

    def print_success(self, message: str, data: Optional[dict] = None) -> None:
        print(f"SUCCESS: {message}")

    def print_warning(self, message: str) -> None:
        print(f"WARNING: {message}")

    def print_info(self, message: str) -> None:
        print(f"INFO: {message}")

    def print_json(self, data: Any) -> None:
        print(json.dumps(data, indent=2, default=str))

    def print_panel(
        self, content: str, title: Optional[str] = None, style: str = "cyan"
    ) -> None:
        console = self._rich_console()
        if console is not None:
            try:
                from rich.panel import Panel

                console.print(Panel(content, title=title, border_style=style))
                return
            except Exception:
                pass
        if title:
            print(f"\n=== {title} ===")
        print(content)
        if title:
            print("=" * (len(title) + 8))

    def print_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        title: Optional[str] = None,
    ) -> None:
        console = self._rich_console()
        if console is not None:
            try:
                from rich.table import Table

                table = Table(title=title)
                for header in headers:
                    table.add_column(header)
                for row in rows:
                    table.add_row(*[str(cell) for cell in row])
                console.print(table)
                return
            except Exception:
                pass
        if title:
            print(f"\n{title}")
            print("-" * len(title))
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        print(header_line)
        print("-" * len(header_line))
        for row in rows:
            print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


_output_controller: Optional[Any] = None


def get_output_controller() -> Any:
    """Return the shared output controller.

    Prefers praisonai-code's controller when installed; otherwise returns the
    self-contained fallback so the train CLI runs standalone.
    """
    global _output_controller
    if _output_controller is None:
        if code_available():
            try:
                console_mod = import_code_module("praisonai_code.cli.output.console")
                _output_controller = console_mod.get_output_controller()
            except Exception:
                _output_controller = _FallbackOutputController()
        else:
            _output_controller = _FallbackOutputController()
    return _output_controller


def set_output_controller(controller: Any) -> None:
    """Override the shared output controller (mainly for tests)."""
    global _output_controller
    _output_controller = controller


# Backwards-friendly alias so ``from ...console import OutputController`` works.
OutputController = _FallbackOutputController
