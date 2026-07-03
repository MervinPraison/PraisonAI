"""Output controller access for the praisonai-bot CLI.

When ``praisonai-code`` is co-installed, delegate to its richer
``OutputController`` so bot commands share the same formatting, modes, and
JSON/stream behaviour as the terminal CLI. When only ``praisonai-bot`` is
installed, fall back to a minimal, dependency-free controller that implements
the small surface the bot commands use (``print``, ``print_info``,
``print_success``, ``print_warning``, ``print_error``, ``print_json``).

C9: the code delegation is lazy (via ``_code_bridge``) so ``praisonai-bot``
keeps no static import of ``praisonai-code``.
"""

from __future__ import annotations

import json as _json
from typing import Any


class _FallbackOutputController:
    """Minimal stdout/stderr controller used when praisonai-code is absent."""

    def print(self, message: str = "") -> None:
        print(message)

    def print_info(self, message: str) -> None:
        print(message)

    def print_success(self, message: str) -> None:
        print(message)

    def print_warning(self, message: str) -> None:
        import sys

        print(message, file=sys.stderr)

    def print_error(self, message: str) -> None:
        import sys

        print(message, file=sys.stderr)

    def print_json(self, data: Any) -> None:
        print(_json.dumps(data, indent=2, default=str))


_fallback_singleton: _FallbackOutputController | None = None


def get_output_controller() -> Any:
    """Return the shared output controller.

    Prefers ``praisonai_code``'s controller when available; otherwise returns a
    process-wide minimal fallback.
    """
    try:
        from praisonai_bot._code_bridge import code_available, import_code_module

        if code_available():
            mod = import_code_module("praisonai_code.cli.app")
            return mod.get_output_controller()
    except Exception:
        pass

    global _fallback_singleton
    if _fallback_singleton is None:
        _fallback_singleton = _FallbackOutputController()
    return _fallback_singleton
